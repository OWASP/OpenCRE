FROM node:lts as build

WORKDIR /code
COPY . /code
RUN yarn install && yarn build

FROM python:3.11.0 as run

COPY --from=build /code /code
WORKDIR /code
RUN pip install -r requirements.txt gunicorn

ENTRYPOINT gunicorn
CMD ["--timeout","800","--workers","8","cre:app"]
