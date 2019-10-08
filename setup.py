#!/usr/bin/python3
#
# This file is part of PyPDM
#
# PyPDM is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#
# Copyright 2018 Olivier Hériveaux, Ledger SAS


from setuptools import setup, find_packages

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name='pypdm',
    version='1.1',
    author='Olivier Heriveaux',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/Ledger-Donjon/pypdm',
    install_requires=['pyserial'],
    packages=find_packages(),
    python_requires=">=3.4")
