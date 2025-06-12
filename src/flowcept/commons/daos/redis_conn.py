"""RedisConn module."""

from redis import Redis, ConnectionPool


class RedisConn:
    """RedisConn DAO class."""

    @staticmethod
    def build_redis_conn_pool(host: str = None, port: str = None, password: str = None, uri: str = None) -> Redis:
        """
        Create a Redis connection using either a URI or host/port.

        If `uri` is provided, it will be used to initialize the Redis connection.
        Otherwise, the connection will fall back to using `host` and `port`.

        Parameters
        ----------
        host : str, optional
            Redis host address. Used only if `uri` is not provided.
        port : str, optional
            Redis port. Used only if `uri` is not provided.
        uri : str, optional
            Full Redis URI. Takes precedence over `host` and `port` if defined.
        password : str, optional
            Password for authenticating with Redis.

        Returns
        -------
        Redis
            An instance of the Redis client with a configured connection pool.
        """
        pool_kwargs = {
            "db": 0,
            "password": password,
            "decode_responses": False,
            "max_connections": 10000,
            "socket_keepalive": True,
            "retry_on_timeout": True,
        }

        if uri:
            pool = ConnectionPool.from_url(uri, **pool_kwargs)
        else:
            pool = ConnectionPool(host=host, port=port, **pool_kwargs)

        return Redis(connection_pool=pool)
