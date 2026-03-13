import './chatbot.scss';

import { sanitize } from 'dompurify';
import { marked } from 'marked';
import React, { useEffect, useRef, useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Button, Container, Form, Grid, Header, Icon } from 'semantic-ui-react';

import { useEnvironment } from '../../hooks';
import { Document } from '../../types';

export const Chatbot = () => {
  type ChatMessage = {
    timestamp: string;
    role: string;
    message: string;
    data: Document[] | null;
    accurate: boolean;
  };

  interface ChatState {
    term: string;
    instructions: string;
    error: string;
  }

  const DEFAULT_CHAT_INSTRUCTIONS = 'Answer in English';
  const INSTRUCTION_PRESETS = [
    'Answer in English',
    'Answer in Chinese',
    'Answer in concise bullet points',
    'Answer in executive summary format',
  ];
  const STARTER_PROMPTS = [
    'How should I prevent command injection in modern web applications?',
    'Give me a practical checklist to prevent SSRF in cloud-native systems.',
    'What controls from OWASP ASVS help prevent broken access control?',
    'Explain secure session management mistakes and mitigations with examples.',
  ];

  const DEFAULT_CHAT_STATE: ChatState = {
    term: '',
    instructions: DEFAULT_CHAT_INSTRUCTIONS,
    error: '',
  };

  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string>('');
  const [chat, setChat] = useState<ChatState>(DEFAULT_CHAT_STATE);
  const [user, setUser] = useState('');
  const [modelName, setModelName] = useState<string>('');

  function getModelDisplayName(name: string): string {
    if (!name) {
      return 'a Large Language Model';
    }
    if (name.startsWith('gemini')) {
      return `Google ${name.replace('gemini-', 'Gemini ').replace(/-/g, ' ')}`;
    }
    if (name.startsWith('gpt')) {
      return `OpenAI ${name.toUpperCase()}`;
    }
    return name;
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
      const threshold = 64;
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
      shouldForceScrollRef.current = false;
    }
  }, [chatMessages]);

  function login() {
    fetch(`${apiUrl}/user`, { method: 'GET' })
      .then((response) => {
        if (response.status === 200) {
          response.text().then((loggedInUser) => setUser(loggedInUser));
        } else {
          window.location.href = `${apiUrl}/login`;
        }
      })
      .catch((fetchError) => {
        console.error('Error checking if user is logged in:', fetchError);
        setError(fetchError instanceof Error ? fetchError.message : 'Network error checking login status');
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
    const resultBlocks: JSX.Element[] = [];

    responses.forEach((txt, i) => {
      if (i % 2 === 0) {
        resultBlocks.push(
          <p
            key={i}
            dangerouslySetInnerHTML={{
              __html: sanitize(marked(txt), { USE_PROFILES: { html: true } }),
            }}
          />
        );
      } else {
        resultBlocks.push(
          <SyntaxHighlighter key={i} style={oneLight}>
            {txt}
          </SyntaxHighlighter>
        );
      }
    });

    return resultBlocks;
  }

  async function onSubmit() {
    if (!chat.term.trim()) return;
    shouldForceScrollRef.current = true;

    const currentTerm = chat.term;
    const currentInstructions = chat.instructions.trim() || DEFAULT_CHAT_INSTRUCTIONS;
    setChat({ ...chat, term: '', instructions: currentInstructions });
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
      body: JSON.stringify({ prompt: currentTerm, instructions: currentInstructions }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text();
          const contentType = response.headers.get('content-type') || '';
          let errorMessage = response.statusText;
          try {
            const json = JSON.parse(text);
            if (json.error) errorMessage = json.error;
            else if (json.message) errorMessage = json.message;
          } catch (parseError) {
            const trimmed = text.trim();
            const looksLikeHtml =
              contentType.includes('text/html') || /^<!doctype html>/i.test(trimmed) || /<html[\s>]/i.test(trimmed);
            if (looksLikeHtml) {
              errorMessage = `Server error (${response.status}). Please check backend logs.`;
            } else if (trimmed) {
              errorMessage = trimmed;
            }
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
            data: data.table,
            accurate: data.accurate,
          },
        ]);
      })
      .catch((fetchError) => {
        console.error('Error fetching answer:', fetchError);
        setError(fetchError instanceof Error ? fetchError.message : 'An unexpected network error occurred');
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
          <strong>{d.name}</strong> - section {d.section ?? d.sectionID}
        </a>
        <div className="reference-link">
          <a href={link}>View in OpenCRE</a>
        </div>
      </div>
    );
  }

  function applyStarterPrompt(prompt: string) {
    setChat((prev) => ({ ...prev, term: prompt }));
  }

  function applyInstructionPreset(instruction: string) {
    setChat((prev) => ({ ...prev, instructions: instruction }));
  }

  const normalizedInstructions = chat.instructions.trim() || DEFAULT_CHAT_INSTRUCTIONS;

  return (
    <Grid textAlign="center" verticalAlign="middle" className="chatbot-layout">
      <Grid.Column>
        <Container className={`chatbot-shell ${hasMessages ? 'has-conversation' : ''}`}>
          <section className="chatbot-hero">
            <div className="hero-kicker">OpenCRE Agent Chat</div>
            <Header as="h1" className="chatbot-title">
              Ask Better Security Questions
            </Header>
            <p className="hero-subtitle">
              Get cybersecurity guidance grounded in OpenCRE-linked standards, with references you can verify.
            </p>
            <div className="hero-meta">
              <span className="meta-pill">Model: {getModelDisplayName(modelName)}</span>
              <span className="meta-pill">Sources: OpenCRE standards and linked documents</span>
            </div>
          </section>

          <div className={`chat-container ${hasMessages ? 'chat-active' : 'chat-landing'}`}>
            <div className="chat-surface">
              {error && (
                <div className="ui negative message">
                  <div className="header">Error</div>
                  <p>{error}</p>
                </div>
              )}

              {!hasMessages && (
                <section className="starter-panel">
                  <div className="starter-title">Try one of these prompts</div>
                  <div className="starter-grid">
                    {STARTER_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        className="starter-chip"
                        onClick={() => applyStarterPrompt(prompt)}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </section>
              )}

              <div className="chat-messages" ref={messagesContainerRef}>
                {chatMessages.map((m, idx) => (
                  <div key={idx} className={`chat-message ${m.role}`}>
                    <div className={`message-avatar ${m.role}`}>{m.role === 'assistant' ? 'OC' : 'You'}</div>
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
                          This answer could not be fully verified against OpenCRE sources. Please validate independently.
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="chat-message assistant">
                    <div className="message-avatar assistant">OC</div>
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
                <div className="scroll-to-bottom-wrap">
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
                </div>
              )}

              <Form className="chat-input" size="large" onSubmit={onSubmit}>
                <div className="chat-input-toolbar">
                  <span className="toolbar-label">Instruction presets</span>
                  <div className="instruction-chips">
                    {INSTRUCTION_PRESETS.map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        className={`instruction-chip ${normalizedInstructions === preset ? 'active' : ''}`}
                        onClick={() => applyInstructionPreset(preset)}
                      >
                        {preset}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="chat-field-grid">
                  <Form.Field>
                    <label>Question</label>
                    <Form.Input
                      fluid
                      value={chat.term}
                      onChange={(e) => setChat({ ...chat, term: e.target.value })}
                      placeholder="Ask a cybersecurity question mapped to OpenCRE..."
                    />
                  </Form.Field>
                  <Form.Field>
                    <label>Instructions</label>
                    <Form.Input
                      fluid
                      value={chat.instructions}
                      onChange={(e) => setChat({ ...chat, instructions: e.target.value })}
                      placeholder={DEFAULT_CHAT_INSTRUCTIONS}
                    />
                  </Form.Field>
                </div>

                <Button primary fluid size="small" disabled={loading || !chat.term.trim()}>
                  <Icon name="send" /> Ask OpenCRE
                </Button>
              </Form>
            </div>
          </div>

          <div className="chatbot-disclaimer">
            <div className="disclaimer-kicker">Privacy & Reliability Notice</div>
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
  );
};
