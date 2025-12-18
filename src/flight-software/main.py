# This is where the magic happens!
# This file is executed on every boot (including wake-boot from deepsleep)
# Created By: Michael Pham
# Modified By: UCubeSat

"""
Built for the PySquared FC Board
Version: 2.0.0
Published: Nov 19, 2024
"""

import gc
import os
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
from lib.pysquared.hardware.sd_card.manager.sd_card import SDCardManager
from lib.pysquared.logger import Logger, LogLevel
from lib.pysquared.nvm.counter import Counter
from lib.pysquared.rtc.manager.microcontroller import MicrocontrollerManager
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

    # with open("/sd/test.txt", "w") as f:
    # f.write("Hello world!\r\n")

    # radio = RFM9xManager(
    #     logger,
    #     config.radio,
    #     spi0,
    #     initialize_pin(logger, board.SPI0_CS0, digitalio.Direction.OUTPUT, True),
    #     initialize_pin(logger, board.RF1_RST, digitalio.Direction.OUTPUT, True),
    # )

    # packet_manager = PacketManager(
    #     logger,
    #     radio,
    #     config.radio.license,
    #     Counter(Register.message_count),
    #     0.2,
    # )

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

    def nominal_power_loop():
        logger.debug(
            "FC Board Stats",
            bytes_remaining=gc.mem_free(),
        )

        # packet_manager.send(config.radio.license.encode("utf-8"))

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
