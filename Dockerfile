# ---------------------------------
# PDM Docker file
# Author: Frost Ming
# Author Email: mianghong@gmail.com
# ---------------------------------
FROM python:3.9-slim

RUN python -m pip install -U pdm

WORKDIR /app

ONBUILD COPY pyproject.toml pyproject.toml
ONBUILD COPY pdm.lock pdm.lock
ONBUILD RUN pdm sync

CMD ["pdm"]

# ---------------------------------
# Using this file
# ---------------------------------
# FROM frostming/pdm
#
# COPY . /app
#
# -- Replace with the correct path to your app's main executable
# CMD ["pdm", "run", "python", "main.py"]
