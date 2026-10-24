# ndoc2md em container: o caminho para macOS Intel, onde o pymupdf 2.x não instala
# (ver README, seção "macOS Intel"). Funciona igual em qualquer máquina com Docker.
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends pandoc \
    && rm -rf /var/lib/apt/lists/*

COPY . /src
RUN pip install --no-cache-dir "/src[pdf]" && rm -rf /src

WORKDIR /dados
ENTRYPOINT ["ndoc2md"]
