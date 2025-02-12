FROM python:3.12-alpine
# We don't use curl or docker-explorer when run locally, but we will keep them here in the event they are used by the
# codecrafters execution environment.
RUN apk add --no-cache 'curl>=7.66'

# Download docker-explorer
ARG docker_explorer_version=v18
RUN curl -Lo /usr/local/bin/docker-explorer https://github.com/codecrafters-io/docker-explorer/releases/download/${docker_explorer_version}/${docker_explorer_version}_linux_amd64
RUN chmod +x /usr/local/bin/docker-explorer

COPY . /app
WORKDIR /app

RUN sed -i -e 's/\r$//' /app/your_docker.sh

ENTRYPOINT ["/app/your_docker.sh"]
