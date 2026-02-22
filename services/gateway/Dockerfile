FROM kong:3.5

# Copy Kong configuration
COPY kong.yaml /etc/kong/kong.yaml

# Set environment variables
ENV KONG_DATABASE=off \
    KONG_DECLARATIVE_CONFIG=/etc/kong/kong.yaml \
    KONG_PROXY_ACCESS_LOG=/dev/stdout \
    KONG_ADMIN_ACCESS_LOG=/dev/stdout \
    KONG_PROXY_ERROR_LOG=/dev/stderr \
    KONG_ADMIN_ERROR_LOG=/dev/stderr

EXPOSE 8000 8001 8443 8444

CMD ["kong", "docker-start"]
