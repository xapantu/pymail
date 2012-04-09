#! /usr/bin/env python2
import os
import pythonmail
os.system("rm db/ -Rf")
os.system("mkdir db")
pythonmail.init_db()
