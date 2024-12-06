#==================================== Base Stage ==========================================
FROM python:3.12.3-slim AS base

WORKDIR /opt/menuflow

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3-pip \
      python3-setuptools \
      python3-wheel \
      libmagic1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade --no-cache-dir pip

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

VOLUME [ "/data" ]

#==================================== Dev Stage ==========================================
FROM base AS dev

RUN apt-get update && apt-get install -y --no-install-recommends \
      git \
      inotify-tools && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt ./

RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . ./

RUN python setup.py --version && \
    pip install --no-cache-dir .[all] && \
    cp menuflow/example-config.yaml . && \
    rm -rf build .git

ENTRYPOINT bash -c "watchmedo auto-restart --recursive --pattern=*.py \
           --ignore-patterns=__init__.py;version.py --directory=. -- /opt/menuflow/run.sh dev"

#==================================== Runtime Stage ==========================================
FROM base AS runtime

COPY . ./

RUN python setup.py --version && \
    pip install --no-cache-dir .[all] && \
    cp menuflow/example-config.yaml . && \
    rm -rf build .git

CMD ["/opt/menuflow/run.sh"]
