import './BodyText.scss';

import React, { useState } from 'react';

export const SearchBody = () => {
  return (
    <div className="index-text">
      <p>
        <strong>
          The Open Source project “OpenCRE “ links all security standards and guidelines together at the level
          of requirements into one harmonized resource: threats, weaknesses, what to verify, how to program,
          how to test, which tool settings, in-depth discussion, training material. Everything organized.
        </strong>
      </p>
      <h2>Examples of use:</h2>
      <p>
        <ul>
          <li>
            <a href="https://zeljkoobrenovic.github.io/opencre-explorer/">Explore</a> our catalog in one list
          </li>
          <li>
            <a href="/cre/764-507">CRE 764-507 </a>: the central ‘multilink’ feature of OpenCRE - one link to
            a common requirement shows its coverage in all the resources plus related requirements
          </li>
          <li>
            <a href="/cre/581-525">CRE 581-525</a>: another example of a multilink page
          </li>
          <li>
            <a href="/smartlink/standard/CWE/611">www.opencre.org/smartlink/standard/CWE/611</a>: the
            ‘smartlink’ feature which uses an existing standard to link to related information
          </li>
          <li>
            <a href="/node/standard/OWASP%20Top%2010%202021">OWASP Top 10 2021</a>
          </li>
          <li>
            <a href="https://zeljkoobrenovic.github.io/opencre-explorer/visuals/force-graph-3d-contains.html">
              Fly
            </a>{' '}
            through our catalog in 3D
          </li>
          <li>
            In the top menu: <a href="/root_cres">Browse</a> to explore our catalog (semantic web) of common
            requirements across development processes, technical controls, etc.
          </li>
          <li>
            In the top menu: <a href="/chatbot">OpenCRE Chat</a> to ask any security question. In
            collaboration with Google, we injected all the standards in OpenCRE into an AI model to create the
            world's first security-specialized chatbot. It provides a more reliable answer, and also a
            reference to the relevant standard text.
          </li>
          <li>
            In the top menu: <a href="/map_analysis">Map Analysis</a> to find how any two standards connect
            with eachother
          </li>
          <li>
            In the top menu: <a href="/search/session">Search</a>
          </li>
        </ul>
      </p>
      <h2>How it works:</h2>
      <p>
        OpenCRE links each section of a standard to the corresponding’Common Requirement’, causing that
        section to also link with all other standards that link to the same requirement. This 1) enables users
        to find all relevant information, 2) facilitates a shared and better understanding of cyber security,
        and 3) allows standard makers to have links that keep working and offer all the information that
        readers need, alleviating their need to cover everything themselves. OpenCRE maintains itself: links
        to OpenCRE in the standard text are scanned automatically.
      </p>
      <p>
        OpenCRE is the brainchild of software security professionals Spyros Gasteratos and Rob van der Veer,
        who joined forces to tackle the complexities and segmentation in current security standards and
        guidelines. They collaborated closely with many initiatives, including SKF, OpenSSF and the Owasp Top
        10 project. OpenCRE is an open-source platform overseen by the OWASP foundation through the
        <a href="https://owasp.org/www-project-integration-standards/"> OWASP Integration standard project</a>
        . The goal is to foster better coordination among security initiatives.
      </p>
      <p>
        The ever-growing list of resources: OWASP standards (Top 10, ASVS, Proactive Controls, Cheat sheets,
        Testing guide, ZAP, Juice shop, SAMM), plus several other sources (CWE, CAPEC, NIST-800 53, NIST-800
        63b, Cloud Control Matrix, ISO27002, and NIST SSDF).
      </p>
      <p>
        For more details, see this
        <a href="https://www.youtube.com/watch?v=TwNroVARmB0"> interview and demo video</a>, read the
        <a href="https://github.com/OWASP/www-project-integration-standards/raw/master/writeups/opencredcslides.pdf">
          {' '}
          OpenCRE slides from the 2023 Appsec conference in Washington DC{' '}
        </a>
        , follow our
        <a href="https://www.linkedin.com/company/96695329"> LinkedIn page </a>, click the diagram below, or{' '}
        contact project leaders Rob van der Veer and Spyros Gasteratos via (rob.vanderveer [at] owasp.org) .
      </p>
      <a href="/opencregraphic2.png" target="_blank">
        <img className="align-middle mx-auto " src="/tn_opencregraphic2.jpg" alt="Diagram" />
      </a>
    </div>
  );
};
