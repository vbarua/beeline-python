import datetime
import beeline
from django.db import connection


class HoneyDBWrapper(object):

    def __call__(self, execute, sql, params, many, context):
        vendor = context['connection'].vendor
        trace_name = "django_%s_query" % vendor

        with beeline.tracer(trace_name):
            beeline.add({
                "type": "db",
                "db.query": sql,
                "db.query_args": params,
            })

            try:
                db_call_start = datetime.datetime.now()
                result = execute(sql, params, many, context)
                db_call_diff = datetime.datetime.now() - db_call_start
                beeline.add_field(
                    "db.duration", db_call_diff.total_seconds() * 1000)
            except Exception as e:
                beeline.add_field("db.error", e)
                raise
            else:
                return result
            finally:
                if vendor == "postgresql" or vendor == "mysql":
                    beeline.add({
                        "db.last_insert_id": context['cursor'].cursor.lastrowid,
                        "db.rows_affected": context['cursor'].cursor.rowcount,
                    })


class HoneyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # Code to be executed for each request before
        # the view (and later middleware) are called.

        db_wrapper = HoneyDBWrapper()
        trace_name = "django_http_%s" % request.method.lower()
        with connection.execute_wrapper(db_wrapper):
            beeline._new_event(data={
                "type": "http_server",
                "request.host": request.get_host(),
                "request.method": request.method,
                "request.path": request.path,
                "request.remote_addr": request.META['REMOTE_ADDR'],
                "request.content_length": request.META['CONTENT_LENGTH'],
                "request.user_agent": request.META['HTTP_USER_AGENT'],
                "request.scheme": request.scheme,
                "request.secure": request.is_secure(),
                "request.query": request.GET,
                "request.xhr": request.is_ajax(),
                "request.post": request.POST
            }, trace_name=trace_name, top_level=True)

            response = self.get_response(request)

            # Code to be executed for each request/response after
            # the view is called.

            beeline.add_field("response.status_code", response.status_code)
            beeline._send_event()

            return response
