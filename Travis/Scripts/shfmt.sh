#!/usr/bin/env bash
#
sudo wget https://raw.githubusercontent.com/jamesmstone/dockerfiles/master/shfmt/Dockerfile
sudo docker build -t jamesmstone/shfmt .
sudo docker run -it --rm -v /home/travis/build/christronyxyocum/tronitor/Travis/Scripts:/sh -w /sh jamesmstone/shfmt -s -i 4 -ci -sr -d travis_usmu.sh
sudo docker run -it --rm -v /home/travis/build/christronyxyocum/tronitor:/sh -w /sh jamesmstone/shfmt -s -i 4 -ci -sr -d usmu.sh
