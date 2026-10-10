#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

# Part of nvGUI4Tesseract, a light and accessible graphical interface for
# handling OCR with Tesseract.
# Copyright (C) 2022 Javi Dominguez
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

import gettext
import locale
import sys

# Definir el dominio de traducción
DOMAIN = "logviewer"
LOCALE_DIR = "locale"

# Inicialización del idioma
try:
	language_code = locale.getdefaultlocale()[0].split("_")[0]
	lancode = locale.normalize(language_code).split("_")[0]
except Exception:
	lancode = 'en'

# Configurar gettext
translation = gettext.translation(
	DOMAIN,
	localedir=LOCALE_DIR,
	languages=[lancode],
	fallback=True,
)
translation.install()
_ = translation.gettext

# Exportar la función _ para uso global si es necesario
sys.modules[__name__].__dict__['_'] = _

