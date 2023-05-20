import './chatbot.scss';

import React, { createElement, useEffect, useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { dark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Button, Comment, Container, Dropdown, Form, GridRow, Header, Icon, Input } from 'semantic-ui-react';
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
    const codeRegex = /```([\s\S]*?)```/g;
    let resp = response;

    let formattedResponse = response.replace(codeRegex, (x, code: string) => {
      const language = (x.match(/```(.*)\n/) || [])[1] || 'none';
      // todo replace this replacer with something that can do templating
      return (
        <SyntaxHighlighter language={language} style={dark}>
          {code}
        </SyntaxHighlighter>
      );
    });
    return formattedResponse;
  }

  function onSubmit() {
    setLoading(true);
    setChatMessages((chatMessages) => [
      ...chatMessages,
      { timestamp: new Date().toLocaleTimeString(), role: 'user', message: chat.term, data: [] },
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
          { timestamp: data.timestamp, role: 'assistant', message: data.response, data: data.table },
        ]);
      })
      .catch((error) => {
        console.error('Error fetching answer:', error);
        setError(error);
        setLoading(false);
      });
  }

  function displayDocument(d: Document) {
    return (
      <a href={d.hyperlink} target="_blank">
        *Reference: The above answer was based on the {d.name} section of {d.section};
      </a>
    );
  }
  return (
    <>
      {user != '' ? '' : login()}
      <LoadingAndErrorIndicator loading={loading} error={error} />
      <Grid textAlign="center" style={{ height: '100vh' }} verticalAlign="middle">
        <Grid.Column verticalAlign="middle">
          <Header as="h1">OWASP Chat-CRE</Header>
          <Container>
            <Grid>
              <GridRow columns={1}>
                <Grid.Column className="chat-container">
                  <div id="chat-messages">
                    {chatMessages.map((m) => (
                      <div id={m.message} className="foobar">
                        <Comment.Group
                          className={
                            m.role == 'user'
                              ? 'right floated six wide column'
                              : 'left floated six wide column'
                          }
                        >
                          <Comment>
                            <Comment.Content>
                              <Comment.Avatar src=""></Comment.Avatar>
                              <Comment.Avatar src=""></Comment.Avatar>
                              <Comment.Author as="b">{m.role}</Comment.Author>
                              <Comment.Metadata>
                                <span className="timestamp">{m.timestamp}</span>
                              </Comment.Metadata>
                              <Comment.Text>{m.message}</Comment.Text>
                              {m.data
                                ? m.data?.map((m2) => {
                                    return displayDocument(m2);
                                  })
                                : ''}
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
            </Grid>
          </Container>
        </Grid.Column>
      </Grid>
    </>
  );
};
