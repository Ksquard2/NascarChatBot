fetch("http://127.0.0.1:5000/")
    .then(response => {
        if (!response.ok) {
            throw new Error("Network response was not ok");
        }
            return response.json(); // Parse JSON
        })
    .then(data => {
        //Place to cook
    })
    .catch(error => {
        console.error("GET error:", error);
    });