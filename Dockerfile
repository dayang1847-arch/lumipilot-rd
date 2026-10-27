FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RD_RUNTIME_DIR=/var/lib/lumipilot-rd
WORKDIR /app
RUN useradd --uid 10001 --create-home rd && mkdir -p /var/lib/lumipilot-rd && chown rd:rd /var/lib/lumipilot-rd
COPY --chown=rd:rd server.py /app/server.py
COPY --chown=rd:rd scripts /app/scripts
COPY --chown=rd:rd templates /app/templates
COPY --chown=rd:rd web /app/web
USER 10001:10001
EXPOSE 8988
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request; from urllib.parse import urlsplit; req=urllib.request.Request('http://127.0.0.1:8988/healthz',headers={'Host':urlsplit(os.environ['RD_PUBLIC_ORIGIN']).netloc}); urllib.request.urlopen(req,timeout=3)"
CMD ["python","server.py"]
