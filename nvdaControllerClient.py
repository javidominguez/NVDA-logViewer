#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

# Part of NVDA Log Viewer, an accessible graphical interface for viewing
# NVDA logs.
# Copyright (C) 2022 Javi Dominguez
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

import ctypes
import sys

# Load the NVDA client library.
if "32 bit" in sys.version:
	clientLib = ctypes.windll.LoadLibrary('./nvdaControllerClient32.dll')
elif "64 bit" in sys.version:
	clientLib = ctypes.windll.LoadLibrary('./nvdaControllerClient64.dll')
else:
	clientLib = None

def message(msg):
	if not clientLib:
		return False
	# Test whether NVDA is running.
	if clientLib.nvdaController_testIfRunning() != 0:
		return False
	# Speak and braille the message.
	try:
		clientLib.nvdaController_cancelSpeech()
		clientLib.nvdaController_speakText(msg)
		clientLib.nvdaController_brailleMessage(msg)
	except Exception:
		return False
	return True
