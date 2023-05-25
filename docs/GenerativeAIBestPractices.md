# Generative AI Design Best Practices for Web Applications
In today’s digital landscape, generative AI has the potential to become an essential capability in web applications, offering personalized and dynamic user experiences.

However, ensuring a secure, user-friendly, and privacy-aware application requires implementing best practices in AI design.

This guide presents five best practices for integrating generative AI in web applications, along with corresponding code examples in Python.

Please note these recommendations are by no means comprehensive and the (generative) code examples are very basic predominantly to help illustrate the point. The aim is to stimulate conversation and continually improve the recommendations. Your feedback is most welcome.

## 1. Distinguish Between General and Private Knowledge:

Determine whether your web application should provide information from your specific private data or a larger foundational data model. If the application use case only your organizations internal data, then set rules in the application to return an error or a message when there are no relevant matches or the similarity score is below a certain threshold. If the application can use the larger foundational data for responses then clearly indicate whether the information comes from general or private knowledge to keep users informed.

Essentially you will need to set a score threshold for your embedding, this is how private/additional knowledge is added to a generative AI model. When a user enters a prompt if none of the private data meets the score threshold, then respond with an error e.g. “We found no relevant information.” . If the web-app is okay to respond with general data then label the response accordingly e.g: “We found no relevant information internally, however here an answer from general knowledge” etc..

<pre><code>
import openai

def handle_query(query, score_threshold=0.5):
    response = openai.Completion.create(engine="davinci-codex", prompt=query, max_tokens=50, n=1, stop=None, temperature=0.5)
    results, score = response.choices[0].text.strip(), response.choices[0].confidence

    if score < score_threshold:
        return "We found no relevant information."
    else:
        return f"From private knowledge: {results}" if is_private_data(query) else f"From general knowledge: {results}"
</code></pre>



## 2. Protect Users’ Private Data by Dynamically Limiting What is sent to the LLM

Avoid design flaws that could compromise user privacy, such as giving a generative AI model access to all customer data. Instead, use “grounding” to provide the AI model with only the relevant data sets for each specific user. This ensures that users will not inadvertently access others’ personal information.

The key point here is never trust user input, and do not leave it to the AI and it’s biases to determine which data to show a user especially since it’s none deterministic. As a result only feed the AI data relevant to the user, when they make a request so even if they try to get it to present other users data, it would not have that information at the time of the request.

<pre><code>
import openai

def get_user_specific_data(user_id):
    # Your logic to fetch user-specific data
    user_data = fetch_user_data(user_id)
    return user_data

def process_query_for_user(query, user_id):
    user_data = get_user_specific_data(user_id)
    user_data_prompt = generate_prompt_from_user_data(user_data)
    response = openai.Completion.create(engine="davinci-codex", prompt=user_data_prompt + query, max_tokens=50, n=1, stop=None, temperature=0.5)
    return response.choices[0].text.strip()
</code></pre>

## 3. Implement a tiered data approach

Organize your data into public, user-specific, and persona-based categories. When sending information to the generative AI, provide only the public knowledge and user-specific knowledge applicable to the signed-in user and their persona. This strategy helps maintain data privacy.

<pre><code>
import openai

def get_tiered_data(user_id):
    public_data = fetch_public_data()
    user_specific_data = fetch_user_specific_data(user_id)
    return public_data, user_specific_data

def process_query_with_tiered_data(query, user_id):
    public_data, user_specific_data = get_tiered_data(user_id)
    combined_prompt = generate_prompt_from_data(public_data, user_specific_data)
    response = openai.Completion.create(engine="davinci-codex", prompt=combined_prompt + query, max_tokens=50, n=1, stop=None, temperature=0.5)
    return response.choices[0].text.strip()
</code></pre>

## 4. Manage authorization for sensitive activities

For activities like purchasing or changing personal information, use a two-step process to ensure user approval. For instance, after a user agrees to a recommendation provided by the generative AI, send them a deep link to review and confirm the action in a separate, secure environment.

<pre><code>
import openai

def get_recommendation(query):
    response = openai.Completion.create(engine="davinci-codex", prompt=query, max_tokens=50, n=1, stop=None, temperature=0.5)
    return response.choices[0].text.strip()

def handle_purchase(user_id, product_id):
    # Your logic to generate a deep link for the user to review and confirm the purchase
    deep_link = generate_deep_link(user_id, product_id)

    # Send the deep link via email or push notification
    send_deep_link(user_id, deep_link)

    return f"We have sent you a link to review and confirm your purchase. Please check your email or notifications."
</code></pre>

## 5. Set Behavioral Restrictions for AI Interactions

Since AI behavior is nondeterministic and prone to errors, it’s crucial to set restrictions that prevent rudeness or inappropriate interactions with users. While most generative AI models are trained to be polite, adding explicit constraints can help avoid potential issues.

<pre><code>
import openai

def filter_inappropriate_responses(response):
    # Your logic to check and filter inappropriate content
    if is_inappropriate(response):
        return "Sorry, I cannot provide the information you're looking for."
    else:
        return response

def process_query(query):
    response = openai.Completion.create(engine="davinci-codex", prompt=query, max_tokens=50, n=1, stop=None, temperature=0.5)
    text = response.choices[0].text.strip()

    # Filter the response for inappropriate content
    filtered_text = filter_inappropriate_responses(text)
    return filtered_text
</code></pre>
