FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Vienna
RUN apt update && apt -y --no-install-recommends upgrade
RUN apt install --no-install-recommends -y \
    tzdata \
    python3-setuptools \
    python3-pip \
    python3-paho-mqtt \
    python3-prometheus-client \
    curl

WORKDIR /usr/src/app
COPY build/main.py /usr/src/app/main.py
# install python modules
COPY ./build/requirements.txt ./
RUN pip3 install --break-system-packages --disable-pip-version-check --no-cache-dir -r requirements.txt
RUN pip3 freeze

# cleanup
# starting at 471MB
# with updates 473MB
# down to 227MB
RUN apt -y purge python3-pip python3-setuptools; \
    apt -y autoremove; \
    apt -y clean;

USER ubuntu
CMD ["python3", "-u", "/usr/src/app/main.py"]
