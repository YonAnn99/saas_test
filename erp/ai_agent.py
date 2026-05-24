import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Cargamos las variables ocultas de tu archivo .env
load_dotenv()

# ==========================================
# CEREBRO EN LA NUBE ULTRARRÁPIDA (GROQ)
# ==========================================
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

def tool_check_inventory(tenant_id, product_query):
    # ... (Tus ojos de la base de datos se quedan EXACTAMENTE igual) ...
    from .models import Product
    try:
        products = Product.objects.filter(
            tenant_id=tenant_id, name__icontains=product_query
        ) | Product.objects.filter(
            tenant_id=tenant_id, sku__icontains=product_query
        )

        if not products.exists():
            return "No encontré ningún producto con ese nombre."

        report = ""
        for p in products:
            status = "¡Stock Crítico!" if p.stock <= p.min_stock_alert else "Stock Normal"
            report += f"- {p.name} (SKU: {p.sku}): {p.stock} unidades a ${p.sale_price}. [{status}]\n"
        
        return report
    except Exception as e:
        return f"Error interno: {str(e)}"

def chat_with_agent(tenant_id, nombre_empresa, user_message, chat_history=None):
    if chat_history is None:
        chat_history = []
        
    # Instrucciones MILITARES: Prohibido hablar de stock sin consultar la BD
    mensajes = [
        {
            "role": "system", 
            "content": f"Eres el asistente de ventas de '{nombre_empresa}'. REGLA ESTRICTA: TIENES COMPLETAMENTE PROHIBIDO decir que no tienes información o preguntar por detalles extra si el usuario menciona productos, SKUs o stock. Siempre debes usar tu herramienta 'tool_check_inventory' con las palabras exactas que te dio el usuario ANTES de dar cualquier respuesta."
        }
    ]

    # Inyectamos el historial de la plática anterior para que no tenga amnesia
    for msg in chat_history:
        mensajes.append(msg)

    # Inyectamos el mensaje actual
    mensajes.append({"role": "user", "content": user_message})

    mis_herramientas = [
        {
            "type": "function",
            "function": {
                "name": "tool_check_inventory",
                "description": "Busca disponibilidad, stock y precio de un producto.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_query": {
                            "type": "string",
                            "description": "Nombre del producto (ej. 'lamina', 'acrilico')"
                        }
                    },
                    "required": ["product_query"]
                }
            }
        }
    ]

    try:
        # Usamos el modelo instantáneo de Llama 3.1 alojado en Groq
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile", 
            messages=mensajes,
            tools=mis_herramientas,
            tool_choice="auto",
        )
        
        response_message = response.choices[0].message

        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                if tool_call.function.name == "tool_check_inventory":
                    argumentos = json.loads(tool_call.function.arguments)
                    query_busqueda = argumentos.get("product_query", "")
                    
                    resultado_db = tool_check_inventory(tenant_id, query_busqueda)
                    
                    mensajes.append(response_message)
                    mensajes.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": "tool_check_inventory",
                        "content": resultado_db,
                    })

            # Segunda llamada para formular la respuesta final
            second_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=mensajes
            )
            return second_response.choices[0].message.content
        else:
            return response_message.content

    except Exception as e:
        return f"Error de conexión con Groq: {str(e)}"