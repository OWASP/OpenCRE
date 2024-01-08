import './chatbot.scss';

import DOMPurify, { sanitize } from 'dompurify';
import { marked } from 'marked';
import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Button, Comment, Container, Form, GridRow, Header, Icon } from 'semantic-ui-react';
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
  interface ResponseMessagePart {
    iscode: boolean;
    message: string;
  }
  const DEFAULT_CHAT_STATE: ChatState = { term: '', error: '' };

  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);

  const [chatMessages, setChatMessages] = useState<chatMessage[]>([]);
  const [error, setError] = useState<string>('');
  const [chat, setChat] = useState<ChatState>(DEFAULT_CHAT_STATE);
  const [user, setUser] = useState('');

  function login() {
    fetch(`${apiUrl}/user`, {
      method: 'GET',
    })
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

  function processResponse(response) {
    const responses = response.split('```');
    let i = 0;
    const res = [<></>];
    for (const txt of responses) {
      if (i % 2 == 0) {
        res.push(
          <p
            dangerouslySetInnerHTML={{
              __html: sanitize(marked(txt), { USE_PROFILES: { html: true } }),
            }}
          />
        );
      } else {
        res.push(<SyntaxHighlighter style={oneLight}>{txt}</SyntaxHighlighter>);
      }
      i++;
    }
    return res;
  }

  function onSubmit() {
    setLoading(true);
    setChatMessages((chatMessages) => [
      ...chatMessages,
      {
        timestamp: new Date().toLocaleTimeString(),
        role: 'user',
        message: chat.term,
        data: [],
        accurate: true,
      },
    ]);

    fetch(`${apiUrl}/completion`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ prompt: chat.term }),
    })
      .then((response) => response.json())
      .then((data) => {
        setLoading(false);
        setError('');
        setChatMessages((chatMessages) => [
          ...chatMessages,
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
    if (d === null || d.doctype === null) {
      return <p>{d}</p>;
    }
    var link = '/node/' + d.doctype.toLowerCase() + '/' + d.name;
    if (d.section) {
      link = link + '/section/' + d.section;
    } else {
      link = link + '/sectionid/' + d.sectionID;
    }
    return (
      <p>
        <p>
          *Reference: The above answer used as preferred input:
          <a href={d.hyperlink} target="_blank">
            {' '}
            {d.name} section: {d.section ? d.section : d.sectionID};
          </a>
        </p>
        <p>
          You can find more information about this section of {d.name} <a href={link}> on its OpenCRE page</a>
        </p>
      </p>
    );
  }

  return (
    <>
      {user != '' ? '' : login()}
      <LoadingAndErrorIndicator loading={loading} error={error} />
      <Grid textAlign="center" style={{ height: '100vh' }} verticalAlign="middle">
        <Grid.Column verticalAlign="middle">
          <Header as="h1">OWASP OpenCRE Chat</Header>
          <Container>
            <Grid>
              <GridRow columns={1}>
                <Grid.Column className="chat-container">
                  <div id="chat-messages">
                    {chatMessages.map((m) => (
                      <div>
                        <Comment.Group
                          className={
                            m.role == 'user'
                              ? 'right floated six wide column'
                              : 'left floated six wide column'
                          }
                        >
                          <Comment>
                            <Comment.Content>
                              <Comment.Author as="b">{m.role}</Comment.Author>
                              <Comment.Metadata>
                                <span className="timestamp">{m.timestamp}</span>
                              </Comment.Metadata>
                              <Comment.Text>{processResponse(m.message)}</Comment.Text>
                              {m.data
                                ? m.data?.map((m2) => {
                                    return displayDocument(m2);
                                  })
                                : ''}
                              {m.accurate ? (
                                ''
                              ) : (
                                <i>
                                  Note: The content of OpenCRE could not be used to answer your question, as
                                  no matching standard was found. The answer therefore has no reference and
                                  needs to be regarded as less reliable. Try rephrasing your question, use
                                  similar topics, or <a href="https://opencre.org">OpenCRE search</a>.
                                </i>
                              )}
                            </Comment.Content>
                          </Comment>
                        </Comment.Group>
                      </div>
                    ))}
                  </div>
                </Grid.Column>
              </GridRow>
              <GridRow columns={1}>
                <Grid.Column>
                  <Form className="chat-input" size="large" onSubmit={onSubmit}>
                    <Form.Input
                      size="large"
                      fluid
                      value={chat.term}
                      onChange={(e) => {
                        setChat({
                          ...chat,
                          term: e.target.value,
                        });
                      }}
                      placeholder="Type your infosec question here..."
                    />
                    <Button fluid size="small" primary onSubmit={onSubmit}>
                      <Icon name="send" />
                    </Button>
                  </Form>
                </Grid.Column>
              </GridRow>
              <div className="table-container mt-5 ms-5 d-none">
                <div className="table-content bg-light shadow p-3" id="table-content"></div>
              </div>
              <div className="chatbot">
                <i>
                  Answers are generated by a Google PALM2 Large Language Model, which uses the internet as
                  training data, plus collected key cybersecurity standards from{' '}
                  <a href="https://opencre.org">OpenCRE</a> as the preferred source. This leads to more
                  reliable answers and adds references, but note: it is still generative AI which is never
                  guaranteed correct.
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
            </Grid>
          </Container>
        </Grid.Column>
      </Grid>
    </>
  );
};
