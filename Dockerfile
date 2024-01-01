FROM node:lts as build

WORKDIR /code
COPY . /code
RUN yarn install && yarn build

FROM python:3.11.0 as run

COPY --from=build /code /code
WORKDIR /code
RUN pip install -r requirements.txt gunicorn

ENTRYPOINT gunicorn
CMD '--bind 0.0.0.0:8081 --log-level debug -w 3 --timeout 800 cre:app'
