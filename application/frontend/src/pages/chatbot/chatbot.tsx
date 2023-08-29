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
  const availableLangs = [
    'oneC (1c)',
    'abnf',
    'accesslog',
    'actionscript',
    'ada',
    'angelscript',
    'apache',
    'applescript',
    'arcade',
    'arduino',
    'armasm',
    'asciidoc',
    'aspectj',
    'autohotkey',
    'autoit',
    'avrasm',
    'awk',
    'axapta',
    'bash',
    'basic',
    'bnf',
    'brainfuck',
    'cLike (c-like)',
    'c',
    'cal',
    'capnproto',
    'ceylon',
    'clean',
    'clojureRepl (clojure-repl)',
    'clojure',
    'cmake',
    'coffeescript',
    'coq',
    'cos',
    'cpp',
    'crmsh',
    'crystal',
    'csharp',
    'csp',
    'css',
    'd',
    'dart',
    'delphi',
    'diff',
    'django',
    'dns',
    'dockerfile',
    'dos',
    'dsconfig',
    'dts',
    'dust',
    'ebnf',
    'elixir',
    'elm',
    'erb',
    'erlangRepl (erlang-repl)',
    'erlang',
    'excel',
    'fix',
    'flix',
    'fortran',
    'fsharp',
    'gams',
    'gauss',
    'gcode',
    'gherkin',
    'glsl',
    'gml',
    'go',
    'golo',
    'gradle',
    'groovy',
    'haml',
    'handlebars',
    'haskell',
    'haxe',
    'hsp',
    'htmlbars',
    'http',
    'hy',
    'inform7',
    'ini',
    'irpf90',
    'isbl',
    'java',
    'javascript',
    'jbossCli (jboss-cli)',
    'json',
    'juliaRepl (julia-repl)',
    'julia',
    'kotlin',
    'lasso',
    'latex',
    'ldif',
    'leaf',
    'less',
    'lisp',
    'livecodeserver',
    'livescript',
    'llvm',
    'lsl',
    'lua',
    'makefile',
    'markdown',
    'mathematica',
    'matlab',
    'maxima',
    'mel',
    'mercury',
    'mipsasm',
    'mizar',
    'mojolicious',
    'monkey',
    'moonscript',
    'n1ql',
    'nginx',
    'nim',
    'nix',
    'nodeRepl (node-repl)',
    'nsis',
    'objectivec',
    'ocaml',
    'openscad',
    'oxygene',
    'parser3',
    'perl',
    'pf',
    'pgsql',
    'phpTemplate (php-template)',
    'php',
    'plaintext',
    'pony',
    'powershell',
    'processing',
    'profile',
    'prolog',
    'properties',
    'protobuf',
    'puppet',
    'purebasic',
    'pythonRepl (python-repl)',
    'python',
    'q',
    'qml',
    'r',
    'reasonml',
    'rib',
    'roboconf',
    'routeros',
    'rsl',
    'ruby',
    'ruleslanguage',
    'rust',
    'sas',
    'scala',
    'scheme',
    'scilab',
    'scss',
    'shell',
    'smali',
    'smalltalk',
    'sml',
    'sqf',
    'sql',
    'sqlMore (sql_more)',
    'stan',
    'stata',
    'step21',
    'stylus',
    'subunit',
    'swift',
    'taggerscript',
    'tap',
    'tcl',
    'thrift',
    'tp',
    'twig',
    'typescript',
    'vala',
    'vbnet',
    'vbscriptHtml (vbscript-html)',
    'vbscript',
    'verilog',
    'vhdl',
    'vim',
    'x86asm',
    'xl',
    'xml',
    'xquery',
    'yaml',
    'zephir',
  ];
  type chatMessage = { timestamp: string; role: string; message: string; data: Document[] | null };
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
    const matchedLang = response.replace(/(\r\n|\n|\r)/gm, '').match(/```(?<lang>\w+).*```/m);
    let lang = 'javascript';
    if (matchedLang) {
      if (matchedLang.groups.lang in availableLangs) {
        lang = matchedLang.groups.lang;
      }
    }
    const responses = response.split('```');
    let i = 0;
    const res = [<></>];
    for (const txt of responses) {
      if (i % 2 == 0) {
        res.push(txt);
      } else {
        res.push(<SyntaxHighlighter style={dark}>{txt}</SyntaxHighlighter>);
      }
      i++;
    }
    return res;
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
          {
            timestamp: new Date().toLocaleTimeString(),
            role: 'assistant',
            message: data.response,
            data: data.table,
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
    var link = '/node/' + d.doctype.toLowerCase() + '/' + d.name;
    if (d.section) {
      link = link + '/section/' + d.section;
    } else {
      link = link + '/sectionid/' + d.sectionID;
    }
    return (
      <p>
        <p>
          *Reference: The above answer was based on:
          <a href={d.hyperlink} target="_blank">
            {' '}
            {d.name} section: {d.section ? d.section : d.sectionID};
          </a>
        </p>
        <p>
          You can find more information about {d.name} <a href={link}> on its OpenCRE page</a>
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
                              <Comment.Author as="b">{m.role}</Comment.Author>
                              <Comment.Metadata>
                                <span className="timestamp">{new Date().toLocaleTimeString()}</span>
                              </Comment.Metadata>
                              <Comment.Text>{processResponse(m.message)}</Comment.Text>
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
              <div className="chatbot">
                <i>
                  ChatCRE uses Google's PALM2 LLM, you can find the code for OpenCRE in
                  https://github.com/owaps/OpenCRE. Your question travels to Heroku (OpenCRE hosting provider)
                  and then to GCP over a protected connection. Your data is never stored in the OpenCRE
                  servers, you can start a new session by refreshing your page. The OpenCRE team has taken all
                  reasonable precautions we could think off to protect your privacy and security.
                </i>
              </div>
            </Grid>
          </Container>
        </Grid.Column>
      </Grid>
    </>
  );
};
