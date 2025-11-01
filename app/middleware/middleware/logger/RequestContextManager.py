import contextvars

class RequestContextManager:
    _request_id_var = contextvars.ContextVar('request_id', default='')
    _client_code_var = contextvars.ContextVar('client_code', default='')
    _user_id_var = contextvars.ContextVar('user_id', default='')

    @staticmethod
    def set_user_id(user_id: str):
        RequestContextManager._user_id_var.set(user_id)

    @staticmethod
    def get_user_id() -> str:
        return RequestContextManager._user_id_var.get()

    @staticmethod
    def set_client_code(client_code: str):
        RequestContextManager._client_code_var.set(client_code)

    @staticmethod
    def get_client_code() -> str:
        return RequestContextManager._client_code_var.get()

    @staticmethod
    def set_request_id(request_id: str):
        RequestContextManager._request_id_var.set(request_id)

    @staticmethod
    def get_request_id() -> str:
        return RequestContextManager._request_id_var.get()

    @staticmethod
    def clear_request_context():
        RequestContextManager._request_id_var.set('')
        RequestContextManager._client_code_var.set('')
        RequestContextManager._user_id_var.set('')
