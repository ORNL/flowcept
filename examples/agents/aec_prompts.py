from typing import Dict, List


def generate_options_set_prompt(layer: int, planned_controls: List[Dict], history: List[Dict] = None,
                                number_of_options=4) -> str:
    max_layers = len(planned_controls)
    prompt_str = f"""
    Role: You are a decision-making expert in Advanced Additive Manufacturing Technologies at the Manufacturing Demonstration Facility.
    Background: You are analyzing layers being printed in a 3D printer. A control decision must be made for each layer to optimize printing outcomes.

    Task: Generate exactly {number_of_options} control options for layer {layer} in a print job with {max_layers} layers.

    Domain Constraints: Each control option must be a JSON object with the following fields: 'power', 'dwell_0', and 'dwell_1'.
    Domain Constraints: 'power' is a float in the range [0, 350]. 'dwell_0' and 'dwell_1' are integers from 10 to 120, divisible by 5.
    """

    if history:
        prompt_str += """
    Context: Use both the original pre-calculated control plan and the full history of previously generated options to inform your decision.
    """
    else:
        prompt_str += """
    Context: Use only the original pre-calculated control plan to inform your decision.
    """

    prompt_str += f"""
    Input - Pre-calculated Control Plan:
    {planned_controls}
    """

    if history:
        prompt_str += f"""
    Input - Full Decision History:
    {history}

    History Format: The history is a list of JSON objects. Each entry includes: the layer index, control options generated for that layer, and the calculated score for each option.
    Scoring Note: Typically (but not always), a lower score indicates a better option.
    """

    prompt_str += f"""
    Format Constraints: Output a list with exactly {number_of_options} elements.
    Format Constraints: Each element must be a JSON object with the format: {{'power': float, 'dwell_0': int, 'dwell_1': int}}.
    Output Restriction: DO NOT WRITE ANYTHING ELSE. Only output the JSON list. The response will be parsed automatically.
    """
    return prompt_str


def choose_option_prompt(scores: Dict, planned_controls: List[Dict], history=None) -> str:
    """
    Prompt: Write the prompt following according to these:

      1. Analyze the prompt. Perform any improvements that you believe will  help the LLM model answer better. Improve the prompt to try to make it more clear, less redundant for the LLM model.
     2. Additionally, the LLM model is often making confusion because it analyzes arrays like [2, 3, 5] to choose a score from it, but it hallucinates saying that it chose the score 5 because it's the lowest score, when it's clearly not the case. Improve the prompt to try to make it more clear for the LLM model.
    3. Analyze each message in the list and use your judgement to identify whether this message is better classified as "human" or as "system.
    4. Rewrite the function to return an array of pairs ("role", "message"), i.e., each element in the array is a tuple of two strings, where "role" should be either "human" or "system". Do not use any MCP message stuff.
    5. Reorganize the function for better readability. Check "if history" only once. Use array.extends to reduce the number of appends. It's fine to use more than 120 characters per line.
    6. Adjust the prompts to better structure the messages themselves, e.g., informing when the message is defining a role, the message content should be "Role: rest of the message"
    Clearly label :
    tasks,
    background,
     format constraints,
     domain constraints,

    """
    current_layer = scores.get("layer")
    max_layers = len(planned_controls)

    prompt_str = f"""
    Role: You are a decision-making expert in Advanced Additive Manufacturing Technologies at the Manufacturing Demonstration Facility.
    Background: You are analyzing a layer-by-layer 3D printing process to help select optimal control decisions based on simulation scores.
    Task: Choose the best control option for layer {current_layer} out of a set of possible options. You will receive the scores and control options computed by an HPC simulation.

    Domain Constraints: Each control option is a dictionary with the fields 'power', 'dwell_0', and 'dwell_1'.
    Domain Constraints: 'power' is a float between 0 and 350. 'dwell_0' and 'dwell_1' are integers between 10 and 120, and must be divisible by 5.

    Score Format: The input is a dictionary with:
    - 'layer': current layer index
    - 'control_options': a list of candidate control option dictionaries
    - 'scores': a list of floats of same length, where scores[i] is the score of control_options[i].

    Scoring Hint: Typically (but not always), a lower score indicates better quality. For example, in [5, 10], option 0 is preferred since 5 < 10.
    ⚠️ Caution: Do NOT hallucinate reasoning. For example, if scores = [2, 3, 5], do NOT say 5 is the lowest. Use correct comparisons only.
    Labeling: If your chosen option has the lowest score, label it 'expected'. If it does not, label it 'surprise' and explain your reasoning.

    Input - Scores for layer {current_layer}:
    {scores}

    Input - Pre-calculated Control Plan:
    {planned_controls}
    """

    if history:
        prompt_str += f"""

    Input - Full History of previous control decisions and scores:
    {history}

    History Format: Each item in the history is a dictionary with keys: 'layer', 'control_options', and 'scores'. Use this to reason based on past behavior.
    """
    else:
        prompt_str += "\nContext: No prior decision history is available. Use only the current inputs.\n"

    prompt_str += """
    Format Constraints: Return a JSON object like:
    {"option": index_of_best_option, "explanation": your_reasoning, "agent_label": "expected" or "surprise"}

    Output Restriction: 
        - DO NOT SAY 'Here is the output'
        - ONLY WRITE THE VALID JSON. NO EXPLANATIONS AT ALL.
        - YOUR OUTPUT MUST BE A VALID JSON! Your output will be parsed programmatically.
    """
    return prompt_str

