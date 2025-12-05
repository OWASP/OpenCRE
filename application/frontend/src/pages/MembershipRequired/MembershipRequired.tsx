import React from 'react';


export const MembershipRequired = () => {
  return (
    <div className="membership-required mt-[20vh] text-center p-4">
      <h1 className="text-3xl font-bold mb-4">
        OWASP Membership Required
      </h1>
      <p className="font-bold text-gray-700 mb-6">
        A OWASP Membership account is needed to login
      </p>
      <a
        href="https://owasp.org/membership/"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center justify-center 
                   px-6 py-3 border border-transparent text-base font-medium rounded-md 
                   text-white bg-blue-600 hover:bg-blue-700 
                   shadow-md transition duration-150 ease-in-out"
      >
        Sign up
      </a>
    </div>
  );
};