import './markdownFromRepo.scss';

import DOMPurify from 'dompurify';
import { marked } from 'marked';
import React, { useEffect, useState } from 'react';

interface MarkdownFromRepoProps {
  src: string;
  className?: string;
  errorHref?: string;
}

const FETCH_TIMEOUT_MS = 10_000;

const githubSourceHref = (src: string, errorHref?: string): string => {
  if (errorHref) {
    return errorHref;
  }
  const repoPath = src.replace(/^\//, '');
  return `https://github.com/OWASP/OpenCRE/blob/main/${repoPath}`;
};

export const MarkdownFromRepo = ({ src, className = '', errorHref }: MarkdownFromRepoProps) => {
  const [html, setHtml] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

    setLoading(true);
    setError(null);

    fetch(src, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to load markdown (${res.status})`);
        }
        return res.text();
      })
      .then((markdown) => {
        const parsed = marked.parse(markdown, { async: false });
        const rendered = DOMPurify.sanitize(String(parsed), {
          USE_PROFILES: { html: true },
        });
        setHtml(rendered);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') {
          setError(err.message);
        }
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [src]);

  if (loading) {
    return <p className="markdown-from-repo__status">Loading…</p>;
  }

  if (error) {
    return (
      <div className="markdown-from-repo__error">
        <p>{error}</p>
        <p>
          View the source on{' '}
          <a href={githubSourceHref(src, errorHref)} target="_blank" rel="noreferrer">
            GitHub
          </a>
          .
        </p>
      </div>
    );
  }

  return (
    <div className={`markdown-from-repo ${className}`.trim()} dangerouslySetInnerHTML={{ __html: html }} />
  );
};
