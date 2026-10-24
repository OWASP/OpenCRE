import './chatbot.scss';

import DOMPurify from 'dompurify';
import { marked } from 'marked';
import React, { useEffect, useRef, useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Button, Container, Form, GridRow, Header, Icon } from 'semantic-ui-react';
import { Grid } from 'semantic-ui-react';

import { useEnvironment } from '../../hooks';
import { Document } from '../../types';

/** Render chatbot markdown safely for dangerouslySetInnerHTML. */
export function renderChatMarkdown(markdown: string): string {
  const parsed = marked.parse(markdown, { async: false });
  return DOMPurify.sanitize(String(parsed), { USE_PROFILES: { html: true } });
}

export const Chatbot = () => {
  type chatMessage = {
    timestamp: string;
    role: string;
    message: string;
    data: Document[] | null;
    accurate: boolean;
    owaspCitations?: string[];
    answerId?: string;
    rating?: 'up' | 'down';
  };

  interface ChatState {
    term: string;
    error: string;
  }

  const DEFAULT_CHAT_STATE: ChatState = { term: '', error: '' };

  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [chatMessages, setChatMessages] = useState<chatMessage[]>([]);
  const [error, setError] = useState<string>('');
  const [chat, setChat] = useState<ChatState>(DEFAULT_CHAT_STATE);
  const [user, setUser] = useState('');
  const [modelName, setModelName] = useState<string>('');

  function getModelDisplayName(modelName: string): string {
    if (!modelName) {
      return 'a Large Language Model';
    }
    // Format model names for display
    if (modelName.startsWith('gemini')) {
      return `Google ${modelName.replace('gemini-', 'Gemini ').replace(/-/g, ' ')}`;
    } else if (modelName.startsWith('gpt')) {
      return `OpenAI ${modelName.toUpperCase()}`;
    }
    return modelName;
  }

  const hasMessages = chatMessages.length > 0;
  // Thumbs only appear when the deployment stores answers; the "not stored" privacy paragraph is then hidden.
  const feedbackOn = chatMessages.some((m) => m.answerId);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const shouldForceScrollRef = useRef(false);
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const threshold = 64; // px from bottom
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;

      setShowScrollToBottom(!isNearBottom);
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const threshold = 120;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;

    if (shouldForceScrollRef.current || isNearBottom) {
      container.scrollTop = container.scrollHeight;
      shouldForceScrollRef.current = false; // reset after use
    }
  }, [chatMessages]);

  function login() {
    fetch(`${apiUrl}/auth/user`, { method: 'GET', headers: { Accept: 'application/json' } })
      .then((response) => {
        if (response.status === 200) {
          response.text().then((user) => setUser(user));
        } else {
          window.location.href = `${apiUrl}/auth/login`;
        }
      })
      .catch((error) => {
        console.error('Error checking if user is logged in:', error);
        setError(error instanceof Error ? error.message : 'Network error checking login status');
        setLoading(false);
      });
  }

  useEffect(() => {
    if (user === '') {
      login();
    }
  }, []);

  function processResponse(response: string) {
    const responses = response.split('```');
    const res: React.ReactElement[] = [];

    responses.forEach((txt, i) => {
      if (i % 2 === 0) {
        res.push(
          <p
            key={i}
            dangerouslySetInnerHTML={{
              __html: renderChatMarkdown(txt),
            }}
          />
        );
      } else {
        res.push(
          <SyntaxHighlighter key={i} style={oneLight}>
            {txt}
          </SyntaxHighlighter>
        );
      }
    });

    return res;
  }

  const HISTORY_CAP = 20;

  /** Thumbs up/down: show the choice at once, tell the server, and undo it if that fails. */
  function rateAnswer(idx: number, rating: 'up' | 'down') {
    const answerId = chatMessages[idx]?.answerId;
    if (!answerId) return;
    const previous = chatMessages[idx].rating;
    const setRating = (value?: 'up' | 'down') =>
      setChatMessages((prev) => prev.map((m, i) => (i === idx ? { ...m, rating: value } : m)));
    setRating(rating);
    fetch(`${apiUrl}/answer_feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ answer_id: answerId, rating }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`rating failed (${res.status})`);
      })
      .catch((err) => {
        console.error(err);
        setRating(previous);
      });
  }

  function startNewChat() {
    setChatMessages([]);
    setError('');
    setChat(DEFAULT_CHAT_STATE);
    setModelName('');
    setShowScrollToBottom(false);
  }

  async function onSubmit() {
    if (!chat.term.trim()) return;
    shouldForceScrollRef.current = true;

    const currentTerm = chat.term;
    setChat({ ...chat, term: '' });
    setLoading(true);

    const prior = chatMessages.slice(-(HISTORY_CAP - 1)).map((m) => ({
      role: m.role === 'assistant' ? 'assistant' : 'user',
      content: m.message,
    }));
    const messages = [...prior, { role: 'user', content: currentTerm }];

    setChatMessages((prev) => [
      ...prev,
      {
        timestamp: new Date().toLocaleTimeString(),
        role: 'user',
        message: currentTerm,
        data: [],
        accurate: true,
      },
    ]);

    fetch(`${apiUrl}/completion`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ prompt: currentTerm, messages }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text();
          let errorMessage = response.statusText;
          try {
            const json = JSON.parse(text);
            if (json.error) errorMessage = json.error;
            else if (json.message) errorMessage = json.message;
          } catch (e) {
            // not json, use text if available
            if (text) errorMessage = text;
          }
          throw new Error(errorMessage || `Error ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        setLoading(false);
        setError('');
        if (data.model_name) {
          setModelName(data.model_name);
        }
        setChatMessages((prev) => [
          ...prev,
          {
            timestamp: new Date().toLocaleTimeString(),
            role: 'assistant',
            message: data.response,
            // CRE RAG citations only — never treat owasp_agent hits as graph nodes.
            data: Array.isArray(data.table)
              ? data.table.filter(
                  (d: Document) =>
                    d &&
                    d.doctype &&
                    !['owaspmeta', 'owasp_meta', 'concept'].includes(String(d.doctype).toLowerCase())
                )
              : data.table,
            accurate: data.accurate,
            owaspCitations: Array.isArray(data?.owasp_agent?.citations) ? data.owasp_agent.citations : [],
            answerId: typeof data?.answer_id === 'string' ? data.answer_id : undefined,
          },
        ]);
      })
      .catch((error) => {
        console.error('Error fetching answer:', error);
        setError(error instanceof Error ? error.message : 'An unexpected network error occurred');
        setLoading(false);
      });
  }

  function displayDocument(d: Document) {
    if (!d || !d.doctype) return null;
    // Never present non-CRE / meta-shaped payloads as OpenCRE graph nodes.
    const dt = String(d.doctype).toLowerCase();
    if (dt === 'owaspmeta' || dt === 'owasp_meta' || dt === 'concept') {
      return null;
    }

    let link = `/node/${d.doctype.toLowerCase()}/${d.name}`;
    link += d.section ? `/section/${d.section}` : `/sectionid/${d.sectionID}`;

    return (
      <div className="reference-card">
        <a href={d.hyperlink} target="_blank" rel="noopener noreferrer">
          <strong>{d.name}</strong> — section {d.section ?? d.sectionID}
        </a>
        {d.embeddingsUrl ? (
          <div className="reference-link">
            <a href={d.embeddingsUrl} target="_blank" rel="noopener noreferrer">
              Scoped source (embedding URL)
            </a>
          </div>
        ) : null}
        <div className="reference-link">
          <a href={link}>View in OpenCRE</a>
        </div>
      </div>
    );
  }

  function displayOwaspCitations(urls: string[]) {
    const safe = urls.filter((url) => {
      try {
        const parsed = new URL(url);
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
      } catch {
        return false;
      }
    });
    if (!safe.length) return null;
    return (
      <div className="references">
        <div className="references-title">OWASP community sources</div>
        {safe.map((url, i) => (
          <div className="reference-card" key={i}>
            <a href={url} target="_blank" rel="noopener noreferrer">
              {url}
            </a>
          </div>
        ))}
      </div>
    );
  }

  return (
    <>
      {/* user login check moved to useEffect */}

      <Grid textAlign="center" verticalAlign="middle" className="chatbot-layout">
        <Grid.Column>
          <Header as="h1" className="chatbot-title">
            OWASP OpenCRE Chat
          </Header>
          {hasMessages ? (
            <div className="chatbot-toolbar">
              <Button type="button" size="small" basic onClick={startNewChat}>
                <Icon name="plus" /> New chat
              </Button>
            </div>
          ) : null}

          <Container>
            <div className={`chat-container ${hasMessages ? 'chat-active' : 'chat-landing'}`}>
              <div className="chat-surface">
                {' '}
                {error && (
                  <div className="ui negative message">
                    <div className="header">Error</div>
                    <p>{error}</p>
                  </div>
                )}
                <div className="chat-messages" ref={messagesContainerRef}>
                  {chatMessages.map((m, idx) => (
                    <div key={idx} className={`chat-message ${m.role}`}>
                      <div className="message-card">
                        <div className="message-header">
                          <span className="message-role">{m.role}</span>
                          <span className="message-timestamp">{m.timestamp}</span>
                        </div>

                        <div className="message-body">{processResponse(m.message)}</div>

                        {m.role === 'assistant' && m.answerId ? (
                          <div className="rate-answer" role="group" aria-label="Rate this answer">
                            <button
                              type="button"
                              className={`rate-btn ${m.rating === 'up' ? 'is-selected' : ''}`}
                              aria-label="Good answer"
                              aria-pressed={m.rating === 'up'}
                              onClick={() => rateAnswer(idx, 'up')}
                            >
                              <Icon name="thumbs up outline" />
                            </button>
                            <button
                              type="button"
                              className={`rate-btn ${m.rating === 'down' ? 'is-selected' : ''}`}
                              aria-label="Bad answer"
                              aria-pressed={m.rating === 'down'}
                              onClick={() => rateAnswer(idx, 'down')}
                            >
                              <Icon name="thumbs down outline" />
                            </button>
                          </div>
                        ) : null}

                        {m.data && m.data.length > 0 && (
                          <div className="references">
                            <div className="references-title">References</div>
                            {m.data.map((d, i) => (
                              <React.Fragment key={i}>{displayDocument(d)}</React.Fragment>
                            ))}
                          </div>
                        )}

                        {m.owaspCitations && m.owaspCitations.length > 0
                          ? displayOwaspCitations(m.owaspCitations)
                          : null}

                        {!m.accurate && (
                          <div className="accuracy-warning">
                            This answer could not be fully verified against OpenCRE sources. Please validate
                            independently.
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="chat-message assistant">
                      <div className="message-card typing-indicator">
                        <span className="dot" />
                        <span className="dot" />
                        <span className="dot" />
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
                {showScrollToBottom && (
                  <button
                    className="scroll-to-bottom"
                    onClick={() => {
                      const container = messagesContainerRef.current;
                      if (container) {
                        shouldForceScrollRef.current = true;
                        container.scrollTop = container.scrollHeight;
                        setShowScrollToBottom(false);
                      }
                    }}
                    aria-label="Scroll to latest message"
                  >
                    <Icon name="arrow down" className="scroll-icon" />
                  </button>
                )}
                <Form className="chat-input" size="large" onSubmit={onSubmit}>
                  <Form.Input
                    fluid
                    value={chat.term}
                    onChange={(e) => setChat({ ...chat, term: e.target.value })}
                    placeholder="Type your infosec question here…"
                  />
                  <Button primary fluid size="small">
                    <Icon name="send" /> Ask
                  </Button>
                </Form>
              </div>
            </div>

            <div className="chatbot-disclaimer">
              <i>
                Answers are generated by {getModelDisplayName(modelName)} Large Language Model, which uses the
                internet as training data, plus collected key cybersecurity standards from{' '}
                <a href="https://opencre.org">OpenCRE</a> as the preferred source. This leads to more reliable
                answers and adds references, but note: it is still generative AI which is never guaranteed
                correct.
                <br />
                <br />
                Model operation is generously sponsored by{' '}
                <a href="https://www.softwareimprovementgroup.com">Software Improvement Group</a>.
                <br />
                {!feedbackOn && (
                  <>
                    <br />
                    Privacy & Security: Your question is sent to Heroku, the hosting provider for OpenCRE, and
                    then to GCP, all via protected connections. Your data isn't stored on OpenCRE servers. The
                    OpenCRE team employed extensive measures to ensure privacy and security. To review the
                    code: https://github.com/owasp/OpenCRE
                  </>
                )}
              </i>
            </div>
          </Container>
        </Grid.Column>
      </Grid>
    </>
  );
};
