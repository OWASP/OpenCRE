import 'swagger-ui-react/swagger-ui.css';

import './docs.scss';

import React, { useEffect } from 'react';
import SwaggerUI from 'swagger-ui-react';

import { MarkdownFromRepo } from '../../components/MarkdownFromRepo/MarkdownFromRepo';
import { useEnvironment } from '../../hooks';

const scrollToHash = () => {
  const hash = window.location.hash.replace('#', '');
  if (!hash) return;
  const el = document.getElementById(hash);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth' });
  }
};

export const Docs = () => {
  const { apiUrl } = useEnvironment();

  useEffect(() => {
    window.scrollTo(0, 0);
    scrollToHash();
  }, []);

  useEffect(() => {
    window.addEventListener('hashchange', scrollToHash);
    return () => window.removeEventListener('hashchange', scrollToHash);
  }, []);

  return (
    <div className="docs-page">
      <header className="docs-page__hero">
        <h1 className="docs-page__title">Documentation</h1>
        <p className="docs-page__subtitle">
          Getting started with OpenCRE, the public REST API, and frequently asked questions.
        </p>
        <nav className="docs-page__nav" aria-label="Docs sections">
          <a href="#getting-started">Getting started</a>
          <a href="#api-reference">API reference</a>
          <a href="#faq">FAQ</a>
          <a href="#resources">Resources</a>
        </nav>
      </header>

      <section id="getting-started" className="docs-section">
        <h2 className="docs-section__title">Getting started</h2>
        <div className="docs-section__body">
          <p>
            OpenCRE unifies security standards and guidelines through Common Requirements (CREs). Use the
            homepage search, <a href="/root_cres">Browse</a>, <a href="/map_analysis">Map Analysis</a>, or the{' '}
            <a href="/chatbot">Chat</a> assistant to explore mapped content.
          </p>
          <p>
            Integrators can use the read-only REST API under <code>{apiUrl}</code>. The OpenAPI specification
            is generated from the backend route registry and validated in CI.
          </p>
        </div>
      </section>

      <section id="api-reference" className="docs-section">
        <h2 className="docs-section__title">API reference</h2>
        <p className="docs-section__intro">
          Interactive documentation for the public API. Raw spec:{' '}
          <a href={`${apiUrl}/openapi.yaml`} target="_blank" rel="noreferrer">
            {apiUrl}/openapi.yaml
          </a>
        </p>
        <div className="docs-page__swagger">
          <SwaggerUI url={`${apiUrl}/openapi.yaml`} docExpansion="list" defaultModelsExpandDepth={0} />
        </div>
      </section>

      <section id="faq" className="docs-section">
        <h2 className="docs-section__title">FAQ</h2>
        <MarkdownFromRepo src="/docs/faq.md" />
      </section>

      <section id="resources" className="docs-section">
        <h2 className="docs-section__title">Resources</h2>
        <ul className="docs-resources">
          <li>
            <a href="https://github.com/OWASP/OpenCRE/blob/main/README.md" target="_blank" rel="noreferrer">
              README
            </a>
          </li>
          <li>
            <a
              href="https://github.com/OWASP/OpenCRE/blob/main/docs/CONTRIBUTING.md"
              target="_blank"
              rel="noreferrer"
            >
              Contributing
            </a>
          </li>
          <li>
            <a
              href="https://github.com/OWASP/OpenCRE/blob/main/docs/my-opencre-user-guide.md"
              target="_blank"
              rel="noreferrer"
            >
              MyOpenCRE user guide
            </a>
          </li>
          <li>
            <a href="https://github.com/OWASP/OpenCRE" target="_blank" rel="noreferrer">
              GitHub repository
            </a>
          </li>
        </ul>
      </section>
    </div>
  );
};

export default Docs;
