# The judge path in a container: docker build -t near-hub . && docker run --rm near-hub
FROM python:3.11-slim
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends make >/dev/null
WORKDIR /app
COPY . .
RUN make setup PYTHON=python3
CMD ["sh", "-c", "make warehouse && make verify"]
