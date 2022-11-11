from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route("/")
def liveness():
    return "Server up!"


@app.route("/interception", methods=["POST"])
def interception():
    data = request.get_json()
    print(data)
    return jsonify(data), 200


if __name__ == "__main__":
    app.run()
