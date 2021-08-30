interface Environment {
  name: string;
  apiUrl: string;
}

const prodEnvironment: Environment = {
  name: 'prod',
  apiUrl: 'https://testcredemo.herokuapp.com/rest/v1',
};

const devEnvironment: Environment = {
  name: 'dev',
  apiUrl: 'http://127.0.0.1:5000/rest/v1',
};

export const useEnvironment = (): Environment =>
  ['127.0.0.1', 'localhost'].includes(window.location.hostname) ? devEnvironment : prodEnvironment;
