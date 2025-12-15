import axios from 'axios';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import React, { useState, useEffect, ReactNode } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Send } from 'lucide-react';
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
  // Removed: const [user, setUser] = useState('');

  // Removed: login function and useEffect hook for authentication

  function processResponse(response) {
    const responses = response.split('```');
    let i = 0;
    const res = [<></>];
    for (const txt of responses) {
      if (i % 2 == 0) {
        res.push(
          <p
            dangerouslySetInnerHTML={{
              __html: DOMPurify.sanitize(marked(txt), { USE_PROFILES: { html: true } }),
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
      return null;
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
          You can find more information about this section of {d.name} <a href={link}>on its OpenCRE page</a>
        </p>
      </p>
    );
  }

  return (
    <div>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="w-full max-w-4xl">
          <h1 className="text-3xl font-bold text-center mb-8">OWASP OpenCRE Chat</h1>
          <div className="w-full">
            {/* Chat Messages Container */}
            <div className="mb-4">
              <div id="chat-messages" className="space-y-4">
                {chatMessages.map((m, index) => (
                  <div
                    key={index}
                    className={`flex ${m.role == 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className="message-card max-w-[60%]"
                      style={{
                        backgroundColor: m.role === 'user' ? '#e3f2fd' : '#c8e6c9',
                        borderRadius: '10px',
                        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
                        padding: '1rem',
                        marginBottom: '1rem',
                      }}
                    >
                      <div className="font-bold mb-1">{m.role}</div>
                      <div className="text-xs text-gray-600 mb-2">{m.timestamp}</div>
                      <div className="text-sm">{processResponse(m.message)}</div>
                      {m.data
                        ? m.data?.map((m2, idx) => {
                          return <div key={idx}>{displayDocument(m2)}</div>;
                        })
                        : ''}
                      {m.accurate ? (
                        ''
                      ) : (
                        <i className="text-xs text-gray-600 mt-2 block">
                          Note: The content of OpenCRE could not be used to answer your question, as
                          no matching standard was found. The answer therefore has no reference and
                          needs to be regarded as less reliable. Try rephrasing your question, use
                          similar topics, or <a href="[https://opencre.org](https://opencre.org)" className="text-blue-600">OpenCRE search</a>.
                        </i>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Chat Input Form */}
            <form
              className="chat-input"
              style={{
                backgroundColor: '#c8e6c9',
                borderRadius: '10px',
                boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
                padding: '1rem',
              }}
              onSubmit={(e) => {
                e.preventDefault();
                onSubmit();
              }}
            >
              <input
                type="text"
                className="w-full px-4 py-3 mb-3 border-0 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={chat.term}
                onChange={(e) => {
                  setChat({
                    ...chat,
                    term: e.target.value,
                  });
                }}
                placeholder="Type your infosec question here..."
              />
              <button
                type="submit"
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-colors"
              >
                <Send size={18} />
              </button>
            </form>

            {/* Disclaimer Text */}
            <div className="mt-6 text-xs text-gray-600 italic text-center px-4">
              <p>
                Answers are generated by a Google PALM2 Large Language Model, which uses the internet as
                training data, plus collected key cybersecurity standards from{' '}
                <a href="[https://opencre.org](https://opencre.org)" className="text-blue-600">OpenCRE</a> as the preferred source. This leads to more
                reliable answers and adds references, but note: it is still generative AI which is never
                guaranteed correct.
              </p>
              <p className="mt-2">
                Model operation is generously sponsored by{' '}
                <a href="[https://www.softwareimprovementgroup.com](https://www.softwareimprovementgroup.com)" className="text-blue-600">Software Improvement Group</a>.
              </p>
              <p className="mt-2">
                Privacy & Security: Your question is sent to Heroku, the hosting provider for OpenCRE, and
                then to GCP, all via protected connections. Your data isn't stored on OpenCRE servers. The
                OpenCRE team employed extensive measures to ensure privacy and security. To review the code:
                [https://github.com/owasp/OpenCRE](https://github.com/owasp/OpenCRE)
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};