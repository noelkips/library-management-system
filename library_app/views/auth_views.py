from http.client import HTTPResponse


def index():
    return HTTPResponse("success")