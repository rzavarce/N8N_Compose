import re

def mask_financial_data(text):
    # Enmascarar números de tarjetas de crédito
    text = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[MASKED_CARD]', text)
    # Enmascarar emails
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[MASKED_EMAIL]', text)
    return text

# Procesar el input en n8n
for item in list(input_data):
    item.json.chatInput = mask_financial_data(item.json.chatInput)

return list(input_data)
