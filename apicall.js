fetch("http://127.0.0.1:5000/llm", {
    method: "POST",
    headers: {
        "Content-Type": "application/json"
    },
    body: JSON.stringify(appointment)
    })
    .then(response => response.json()) 
    .then(data => {
    })
    .catch(error => {
        console.error("POST error:", error);
    });