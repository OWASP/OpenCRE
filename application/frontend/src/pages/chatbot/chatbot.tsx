import './chatbot.scss';

import DOMPurify, { sanitize } from 'dompurify';
import { marked } from 'marked';
import React, { useEffect, useRef, useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Button, Container, Form, GridRow, Header, Icon } from 'semantic-ui-react';
import { Grid } from 'semantic-ui-react';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';

export const Chatbot = () => {
  type chatMessage = {
    timestamp: string;
    role: string;
    message: string;
    data: Document[] | null;
    accurate: boolean;
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
    fetch(`${apiUrl}/user`, { method: 'GET' })
      .then((response) => {
        if (response.status === 200) {
          response.text().then((user) => setUser(user));
        } else {
          window.location.href = `${apiUrl}/login`;
        }
      })
      .catch((error) => {
        console.error('Error checking if user is logged in:', error);
        setError(error);
        setLoading(false);
      });
  }

  function processResponse(response: string) {
    const responses = response.split('```');
    const res: JSX.Element[] = [];

    responses.forEach((txt, i) => {
      if (i % 2 === 0) {
        res.push(
          <p
            key={i}
            dangerouslySetInnerHTML={{
              __html: sanitize(marked(txt), { USE_PROFILES: { html: true } }),
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

  async function onSubmit() {
    if (!chat.term.trim()) return;
    shouldForceScrollRef.current = true;

    const currentTerm = chat.term;
    setChat({ ...chat, term: '' });
    setLoading(true);

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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: currentTerm }),
    })
      .then((response) => response.json())
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
            data: data.table,
            accurate: data.accurate,
          },
        ]);
      })
      .catch((error) => {
        console.error('Error fetching answer:', error);
        setError(error);
        setLoading(false);
      });
  }

  function displayDocument(d: Document) {
    if (!d || !d.doctype) return null;

    let link = `/node/${d.doctype.toLowerCase()}/${d.name}`;
    link += d.section ? `/section/${d.section}` : `/sectionid/${d.sectionID}`;

    return (
      <div className="reference-card">
        <a href={d.hyperlink} target="_blank" rel="noopener noreferrer">
          <strong>{d.name}</strong> — section {d.section ?? d.sectionID}
        </a>
        <div className="reference-link">
          <a href={link}>View in OpenCRE</a>
        </div>
      </div>
    );
  }

  return (
    <>
      {user !== '' ? null : login()}

      <Grid textAlign="center" verticalAlign="middle" className="chatbot-layout">
        <Grid.Column>
          <Header as="h1" className="chatbot-title">
            OWASP OpenCRE Chat
          </Header>

          <Container>
            <div className={`chat-container ${hasMessages ? 'chat-active' : 'chat-landing'}`}>
              <div className="chat-surface">
                {' '}
                {error && (
                  <div className="ui negative message">
                    <div className="header">Document could not be loaded</div>
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

                        {m.data && m.data.length > 0 && (
                          <div className="references">
                            <div className="references-title">References</div>
                            {m.data.map((d, i) => (
                              <React.Fragment key={i}>{displayDocument(d)}</React.Fragment>
                            ))}
                          </div>
                        )}

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
                <br />
                Privacy & Security: Your question is sent to Heroku, the hosting provider for OpenCRE, and
                then to GCP, all via protected connections. Your data isn't stored on OpenCRE servers. The
                OpenCRE team employed extensive measures to ensure privacy and security. To review the code:
                https://github.com/owasp/OpenCRE
              </i>
            </div>
          </Container>
        </Grid.Column>
      </Grid>
    </>
  );
};
