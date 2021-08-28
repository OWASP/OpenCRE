## Frontend

This is a simple React app, written with TypeScript, utilising react-router for routing. Make sure that you have format-on-save turned on in your editor, so prettier and eslint will keep your code looking great (alternatively run `yarn lint` occasionally).

### Getting started

To run the project, you will need to run the following commands

- To install dependencies, run `yarn install`
- To run the app, use `yarn start`, which will run it on localhost:9001
- When running like this, ensure that you have the backend running as well

If you wish to run the entire application from the docker container, you will first need to build the frontend into a single file, which can be done with

- `yarn build`

This will put index.html and bundle.js in the /frontend/www directory, where the docker container can pull it from.
