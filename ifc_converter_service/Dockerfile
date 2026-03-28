FROM aecgeeks/ifcopenshell:latest

USER root

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu/hdf5/serial \
    PORT=8080 \
    STORAGE_ROOT=/data \
    VERIFY_SSL=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    libhdf5-103 \
    libhdf5-cpp-103 \
    libhdf5-dev \
    python3 \
    python3-pip \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g 3d-tiles-tools \
    && if [ -f /usr/lib/x86_64-linux-gnu/hdf5/serial/libhdf5_serial_cpp.so.103 ] && [ ! -f /usr/lib/x86_64-linux-gnu/libhdf5_serial_cpp.so.103 ]; then ln -s /usr/lib/x86_64-linux-gnu/hdf5/serial/libhdf5_serial_cpp.so.103 /usr/lib/x86_64-linux-gnu/libhdf5_serial_cpp.so.103; fi \
    && if [ -f /usr/lib/x86_64-linux-gnu/hdf5/serial/libhdf5_serial.so.103 ] && [ ! -f /usr/lib/x86_64-linux-gnu/libhdf5_serial.so.103 ]; then ln -s /usr/lib/x86_64-linux-gnu/hdf5/serial/libhdf5_serial.so.103 /usr/lib/x86_64-linux-gnu/libhdf5_serial.so.103; fi \
    && ldconfig \
    && find /usr/lib -name libhdf5_serial_cpp.so.103 | grep -q . \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python3 -m pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

RUN mkdir -p /data /app/tmp

EXPOSE 8080

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
