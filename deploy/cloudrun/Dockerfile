# Runtime for the monthly refit on Cloud Run. Generic Python + git + Azure CLI;
# the application code and its Python dependencies come from the GitHub clone at
# run time, so this image only rebuilds when the runtime itself changes.
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git openssh-client curl jq ca-certificates build-essential \
 && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY deploy/cloudrun/bootstrap.sh /usr/local/bin/bootstrap.sh
RUN chmod +x /usr/local/bin/bootstrap.sh

ENTRYPOINT ["/usr/local/bin/bootstrap.sh"]
