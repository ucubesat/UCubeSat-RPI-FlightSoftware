# This is where the magic happens!
# This file is executed on every boot (including wake-boot from deepsleep)
# Created By: Michael Pham
# Modified By: UCubeSat

"""
Built for the PySquared FC Board
Version: 2.0.0
Published: Nov 19, 2024
"""

import binascii
import gc
import math
import os
import struct
import time

import digitalio
import microcontroller
from busio import SPI

try:
    from board_definitions import proveskit_rp2040_v4 as board
except ImportError:
    import board

# SD card
# Arducam imports
from Arducam.Arducam import OV2640, ArducamClass, OV2640_1600x1200
from lib.proveskit_rp2040_v4.register import Register
from lib.pysquared.config.config import Config
from lib.pysquared.hardware.busio import _spi_init, initialize_i2c_bus
from lib.pysquared.hardware.digitalio import initialize_pin
from lib.pysquared.hardware.radio.manager.rfm9x import RFM9xManager
from lib.pysquared.hardware.sd_card.manager.sd_card import SDCardManager
from lib.pysquared.logger import Logger, LogLevel
from lib.pysquared.nvm.counter import Counter
from lib.pysquared.rtc.manager.microcontroller import MicrocontrollerManager
from pysquared.beacon import Beacon
from pysquared.hardware.radio.packetizer.packet_manager import PacketManager
from version import __version__

boot_time: float = time.time()

rtc = MicrocontrollerManager()

(boot_count := Counter(index=Register.boot_count)).increment()
error_count: Counter = Counter(index=Register.error_count)

logger: Logger = Logger(
    error_counter=error_count,
    colorized=False,
    log_level=LogLevel.DEBUG,  # Change this back to INFO before launch
)

logger.info(
    "Booting",
    hardware_version=os.uname().version,
    software_version=__version__,
)


def init_camera(
    cs_pin,
):  # TODO: Find somewhere to put this, own library or pysquared? i have no idea where to put our stuff tbh
    cam = ArducamClass(OV2640, spi=spi0, cs_pin=cs_pin, i2c=i2c1)

    cam.Camera_Detection()
    cam.Spi_Test()
    cam.Camera_Init()
    cam.clear_fifo_flag()
    cam.OV2640_set_JPEG_size(OV2640_1600x1200)
    cam.SPI_CS_HIGH()

    cam.spi.unlock()
    cam.i2c.unlock()

    return cam


def transmit_file(
    logger: Logger, packet_manager: PacketManager, file_path: str, chunk_size: int
):
    """
    Transmit a file using provided packet_manager, chunking the file as specified with `chunk_size`.
    Transmits the file CRC, individual chunk CRC and index, and the file itself.

    Args:
        logger: PySquared logger
        packet_manager: PacketManager to transmit on
        file_path: path to file to transmit
        chunk_size: size of each chunk to transmit
    """

    INDICATE_START = 0x01
    INDICATE_DATA = 0x02
    INDICATE_END = 0x03

    img_size = os.stat(file_path)[6]
    total_chunks = math.ceil(img_size / chunk_size)

    file_crc = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            file_crc = binascii.crc32(chunk, file_crc)

    logger.debug(f"transmitting image with {total_chunks} portions")
    packet_manager.send("fmstl")  # temporary indicator ofc
    packet_manager.send(struct.pack("<BII", INDICATE_START, total_chunks, file_crc))

    chunk_index = 0
    with open(file_path, "rb") as f:
        chunk = f.read(chunk_size)
        while chunk:
            crc32 = binascii.crc32(chunk)

            packed_chunk = (
                struct.pack("<BII", INDICATE_DATA, crc32, chunk_index) + chunk
            )
            time.sleep(3)

            logger.debug(f"sending packed chunk with length {len(packed_chunk)}")
            packet_manager.send(packed_chunk)

            chunk = f.read(chunk_size)
            chunk_index += 1

    packet_manager.send(struct.pack("<B", INDICATE_END))
    logger.debug(f"finished sending {img_size} bytes with {total_chunks} chunks")


try:
    # loiter_time: int = 5
    # for i in range(loiter_time):
    # logger.info(f"Code Starting in {loiter_time-i} seconds")
    # time.sleep(1)
    logger.info("Code starting")

    # watchdog = Watchdog(logger, board.WDT_WDI)
    # watchdog.pet()

    logger.debug("Initializing Config")
    config: Config = Config("config.json")

    spi0: SPI = _spi_init(
        logger,
        board.GP18,  # SCK
        board.GP19,  # MOSI
        board.GP16,  # MISO
    )
    sd_cs = board.GP17
    sd_baudrate = 400000

    logger.debug("Mounting SD card")
    try:
        sd_manager = SDCardManager(
            spi_bus=spi0, chip_select=sd_cs, baudrate=sd_baudrate
        )
        logger.debug("Succesfully mounted SD card")
    except Exception as e:
        logger.critical("Failed to mount microSD card", e)

    radio = RFM9xManager(
        logger,
        config.radio,
        spi0,
        initialize_pin(logger, board.GP3, digitalio.Direction.OUTPUT, True),
        initialize_pin(logger, board.GP6, digitalio.Direction.OUTPUT, True),
    )

    packet_manager = PacketManager(
        logger,
        radio,
        config.radio.license,
        Counter(Register.message_count),
        0.2,
    )

    i2c1 = initialize_i2c_bus(
        logger,
        board.GP9,
        board.GP8,
        100000,
    )

    logger.debug("Initializing cameras")
    cam1_cs = digitalio.DigitalInOut(board.GP5)
    cam1_cs.direction = digitalio.Direction.OUTPUT
    cam1_cs.value = False

    cam2_cs = digitalio.DigitalInOut(board.GP4)
    cam2_cs.direction = digitalio.Direction.OUTPUT
    cam2_cs.value = False

    try:
        logger.debug("attempting to initialize camera 1")
        cam1 = init_camera(cam1_cs)

        logger.debug("attempting to initialize camera 2")
        cam2 = init_camera(cam2_cs)
    except Exception as e:
        logger.critical("Failed to initialize camera", e)

    for cam in [cam1, cam2]:
        if not cam.Camera_Detection():
            logger.critical("Camera not detected")

        cam.clear_fifo_flag()
        cam.spi.unlock()
        cam.i2c.unlock()

    logger.info("Taking test image on cam 1")
    bytes_written = cam1.capture_image_buffered(
        logger, file_path="/sd/sample-image-cam1.jpg"
    )
    logger.info(f"Done. {bytes_written} bytes written to SD.")

    logger.info("Taking test image on cam 2")
    bytes_written = cam2.capture_image_buffered(
        logger, file_path="/sd/sample-image-cam2.jpg"
    )
    logger.info(f"Done. {bytes_written} bytes written to SD.")

    # magnetometer = LIS2MDLManager(logger, i2c1)

    # imu = LSM6DSOXManager(logger, i2c1, 0x6B)

    # sleep_helper = SleepHelper(logger, config, watchdog)

    # cdh = CommandDataHandler(logger, config, packet_manager)

    # beacon = Beacon(
    #     logger,
    #     config.cubesat_name,
    #     packet_manager,
    #     boot_time,
    #     imu,
    #     magnetometer,
    #     radio,
    #     error_count,
    #     boot_count,
    # )

    beacon = Beacon(
        logger,
        config.cubesat_name,
        packet_manager,
        boot_time,
        radio,
        error_count,
        boot_count,
    )

    logger.info("Sending radio license directly via packet_manager")
    packet_manager.send(config.radio.license.encode("utf-8"))

    logger.info("Sending test beacon")
    beacon.send()

    def nominal_power_loop():
        # logger.debug(
        #     "FC Board Stats",
        #     bytes_remaining=gc.mem_free(),
        # )
        time.sleep(5)
        gc.collect()
        transmit_file(
            logger, packet_manager, "/sd/sample-image-cam2.jpg", int(gc.mem_free() / 4)
        )

        # beacon.send()

        # cdh.listen_for_commands(10)

        # beacon.send()

        # cdh.listen_for_commands(config.sleep_duration)

    try:
        logger.info("Entering main loop")
        while True:
            # TODO(nateinaction): Modify behavior based on power state
            nominal_power_loop()

    except Exception as e:
        logger.critical("Critical in Main Loop", e)
        time.sleep(10)
        microcontroller.on_next_reset(microcontroller.RunMode.NORMAL)
        microcontroller.reset()
    finally:
        logger.info("Going Neutral!")

except Exception as e:
    logger.critical("An exception occured within main.py", e)
