ARG POSTGRES_IMAGE=postgres:15.18-alpine@sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f
FROM ${POSTGRES_IMAGE}

ARG PATRONI_VERSION=4.1.4

RUN apk add --no-cache \
      curl \
      py3-pip \
      py3-psycopg2 \
      python3 \
      su-exec \
    && pip3 install --no-cache-dir --break-system-packages "patroni[etcd3]==${PATRONI_VERSION}" \
    && patroni --version

COPY deploy/ha/patroni/render_patroni_config.py /usr/local/bin/render-patroni-config
COPY deploy/ha/patroni/patroni-entrypoint.sh /usr/local/bin/patroni-entrypoint

RUN chmod 0755 /usr/local/bin/render-patroni-config /usr/local/bin/patroni-entrypoint \
    && mkdir -p /etc/patroni /var/run/postgresql \
    && chown postgres:postgres /etc/patroni /var/run/postgresql

EXPOSE 5432 8008
ENTRYPOINT ["/usr/local/bin/patroni-entrypoint"]
CMD ["patroni", "/etc/patroni/patroni.yml"]
