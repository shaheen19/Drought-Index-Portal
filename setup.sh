#!/bin/bash

# This is an attempt to automate the process of setting up a computer to run a DASH app.
# To make this file work do this:

# 1) Add "export PATH=$PATH:/bin" to .profile or .bash_profile
# 2) Make this file executable using "chmod u+x setup.sh"
# 3) Ideally, run the line "./setup.sh" and wait!

# Things to do:

# 1) Turn paths into variables. Use this site:
	# "https://www.taniarascia.com/how-to-create-and-use-bash-scripts/"
# 2) Plenty more I'm sure...

echo -- Is this where want to install everything, y/n?

read response

if [ $response = y ] || [ $response = Y ] || [ $response = yes ] || [ $response = Yes ]
then
    echo -- Ok, got it, installing everything into $PWD
    echo -- Updating apt-get and python

    sudo apt-get update && sudo atp-get upgrade
    sudo apt-get install nginx
    sudo apt-get install software-properties-common
    sudo add-apt-repository ppa:deadsnakes/ppa
    sudo apt-get update
    sudo apt-get install python3.6 python3.6-dev
    curl https://bootstrap.pypa.io/get-pip.py | sudo python3.6
    sudo apt-get install nginx


fi
