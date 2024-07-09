FROM node:lts as build
LABEL org.opencontainers.image.source = "https://github.com/OWASP/OpenCRE"
WORKDIR /code
COPY . /code
RUN yarn install && yarn build

FROM python:3.11 as run

COPY --from=build /code /code
WORKDIR /code
COPY ./scripts/prod-docker-entrypoint.sh /code
RUN pip install -r requirements.txt gunicorn

ENV INSECURE_REQUESTS=1
ENV FLASK_CONFIG="production"
RUN chmod +x /code/prod-docker-entrypoint.sh
ENTRYPOINT ["/code/prod-docker-entrypoint.sh"]
