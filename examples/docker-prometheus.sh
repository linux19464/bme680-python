docker run \
  -d \
    -p 9090:9090 \
    -v ./prometheus.yml:/etc/prometheus/prometheus.yml \
  --add-host=host.docker.internal:host-gateway \
    prom/prometheus