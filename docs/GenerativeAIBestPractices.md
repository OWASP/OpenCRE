# Generative AI Design Best Practices for Web Applications
In today’s digital landscape, generative AI has the potential to become an essential capability in web applications, offering personalized and dynamic user experiences.

However, ensuring a secure, user-friendly, and privacy-aware application requires implementing best practices in AI design.

This guide presents five best practices for integrating generative AI in web applications, along with corresponding code examples in Python.

Please note these recommendations are by no means comprehensive and the (generative) code examples are very basic predominantly to help illustrate the point. The aim is to stimulate conversation and continually improve the recommendations. Your feedback is most welcome.

## 1. Distinguish Between General and Private Knowledge:

Determine whether your web application should provide information from your specific private data or a larger foundational data model. If the application use case only your organizations internal data, then set rules in the application to return an error or a message when there are no relevant matches or the similarity score is below a certain threshold. If the application can use the larger foundational data for responses then clearly indicate whether the information comes from general or private knowledge to keep users informed.

Essentially you will need to set a score threshold for your embedding, this is how private/additional knowledge is added to a generative AI model. When a user enters a prompt if none of the private data meets the score threshold, then respond with an error e.g. “We found no relevant information.” . If the web-app is okay to respond with general data then label the response accordingly e.g: “We found no relevant information internally, however here an answer from general knowledge” etc..

## 2. Protect Users’ Private Data by Dynamically Limiting What is sent to the LLM

Avoid design flaws that could compromise user privacy, such as giving a generative AI model access to all customer data. Instead, use “grounding” to provide the AI model with only the relevant data sets for each specific user. This ensures that users will not inadvertently access others’ personal information.

The key point here is never trust user input, and do not leave it to the AI and it’s biases to determine which data to show a user especially since it’s none deterministic. As a result only feed the AI data relevant to the user, when they make a request so even if they try to get it to present other users data, it would not have that information at the time of the request.

## 3. Implement a tiered data approach

Organize your data into public, user-specific, and persona-based categories. When sending information to the generative AI, provide only the public knowledge and user-specific knowledge applicable to the signed-in user and their persona. This strategy helps maintain data privacy.

## 4. Manage authorization for sensitive activities

For activities like purchasing or changing personal information, use a two-step process to ensure user approval. For instance, after a user agrees to a recommendation provided by the generative AI, send them a deep link to review and confirm the action in a separate, secure environment.

## 5. Set Behavioral Restrictions for AI Interactions

Since AI behavior is nondeterministic and prone to errors, it’s crucial to set restrictions that prevent rudeness or inappropriate interactions with users. While most generative AI models are trained to be polite, adding explicit constraints can help avoid potential issues.
