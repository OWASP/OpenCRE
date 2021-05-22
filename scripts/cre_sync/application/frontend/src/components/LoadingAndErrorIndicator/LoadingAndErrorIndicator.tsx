import React, { FunctionComponent } from 'react';
import { Icon, Loader, Message } from 'semantic-ui-react';

interface LoadingAndErrorIndicatorProps {
  loading: boolean;
  error: string | Object | null;
}

export const LoadingAndErrorIndicator: FunctionComponent<LoadingAndErrorIndicatorProps> = ({
  loading,
  error,
}) => {
  return (
    <>
      {loading && <Loader inline="centered" size="huge" active={loading} />}
      {!loading && error && (
        <Message icon negative floating>
          <Icon name="warning" />
          <Message.Content>
            {typeof error === 'string' ? error : 'Document could not be loaded'}
          </Message.Content>
        </Message>
      )}
    </>
  );
};
