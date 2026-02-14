#!/bin/bash

set -e

echo "Don't actually run this! It probably won't work, just use this as a general guide for what needs to be run."
echo -e "\nrunning anyway in 3 seconds..."
sleep 3

sudo apt-get update
sudo apt-get -y upgrade
sudo apt-get install -y python3-pip
sudo apt install --upgrade python3-setuptools

sudo apt install python3-venv
python3 -m venv env --system-site-packages
source env/bin/activate

cd ~
pip3 install --upgrade adafruit-python-shell
wget https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/master/raspi-blinka.py
sudo -E env PATH=$PATH python3 raspi-blinka.py

cd UCubeSat-RPI-FlightSoftware

sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_serial_hw 0
sudo raspi-config nonint do_ssh 0
sudo raspi-config nonint do_camera 0
sudo raspi-config nonint disable_raspi_config_at_boot 0

python3 blinka_test.py