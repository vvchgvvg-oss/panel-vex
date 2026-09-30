FROM python:3.11-slim
RUN groupadd -r paneluser && useradd -r -g paneluser -d /app -s /sbin/nologin paneluser
# docker CLI (اختياري) — يُستخدم لتشغيل كل ملف داخل حاوية خاصة به عند توفر Docker
RUN apt-get update && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/* || true
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py sandbox_runner.py isolation.py ./
RUN mkdir -p /app/panel_data/users_data /app/panel_data/backups /app/panel_data/temp && chown -R paneluser:paneluser /app
USER paneluser
EXPOSE 5000
ENV PORT=5000
ENV PYTHONUNBUFFERED=1
# auto = حاوية لكل ملف عند توفر Docker، وإلا العزل المُقوّى (sandbox)
ENV ISO_MODE=auto
ENV ISO_MEMORY=512m
ENV ISO_CPUS=0.5
ENV ISO_PIDS=128
ENV ISO_NETWORK=none
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen(chr(104)+chr(116)+chr(116)+chr(112)+'://localhost:5000/login')" || exit 1
CMD ["python", "main.py"]
