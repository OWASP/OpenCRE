FROM node:lts as build
LABEL org.opencontainers.image.source = "https://github.com/OWASP/OpenCRE"
WORKDIR /code
RUN apt-get update && apt-get install -y chromium
COPY . /code
RUN yarn install && yarn build

FROM python:3.11 as run

COPY --from=build /code /code
WORKDIR /code
COPY ./scripts/prod-docker-entrypoint.sh /code
# Staging Compose may pass requirements-dev.txt (Librarian ML / OIE Module C.2).
# Default stays prod requirements.txt for Heroku slug size.
ARG REQUIREMENTS_FILE=requirements.txt
RUN pip install -r "${REQUIREMENTS_FILE}" gunicorn

ENV INSECURE_REQUESTS=1
ENV FLASK_CONFIG="production"
RUN chmod +x /code/prod-docker-entrypoint.sh
ENTRYPOINT ["/code/prod-docker-entrypoint.sh"]
