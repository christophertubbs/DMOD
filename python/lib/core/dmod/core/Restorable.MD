# Restorable

A `Restorable` object is an object that defines special rules for serialization that may be deserialized into a
`RestoredPackage` and rebuilt.

## Steps
1. A `Restorable` object packages itself up
   - This creates a dictionary that is `json` serializable
2. The dictionary is serialized into `json` and transmitted somewhere
3. The `json` string/bytes are deserialized back into a dictionary
4. A `RestoredPackage` package is created from the dictionary
5. That `RestoredPackage` may be called to regenerate values from its specification

## What does a `Restorable` produce?

The `Restorable.create_restorable_package` function will produce a dictionary that looks like the following (as of 2024/01/31):

| Field       | Description                                           |
|-------------|-------------------------------------------------------|
| module      | Where to find the object to restore                   |
| name        | The name of the object to restore                     |
| args        | Positional Arguments to use when restoring the object |
| kwargs      | Keyword arguments to use when restoring the object    |
| is_function | Whether the final result should be callable           |

### Example:

```python
packaged_instance = {
    "module": "some.util.package",
    "name": "RedisWhatever",
    "kwargs": {
        "db": 0,
        "channel": "example",
        "host": {
            "module": "some.settings.package",
            "name": "redis.HOST"
        },
        "username": {
            "module": "some.auth.package",
            "name": "get_redis_username"
        },
        "password": {
            "module": "some.auth.package",
            "name": "get_redis_password"
        },
        "handlers": {
            "receive": [
                {
                    "module": "some.processing.package",
                    "name": "inform_clients",
                    "is_function": True
                }
            ]
        }
    }
}
```

### What happens with the dictionary from the `Restorable`?

The first step to using that dictionary is to create a `PackagedRestorable` from that dictionary. If that dictionary is 
named `create_packaged_instance`, this is done by calling something like `package = RestoredPackage(**packaged_instance)`.
To get the restored item, you would call `package.restore()` or simply `package()`.

The following examples all produce the same result:

```python
RestoredPackage(**packaged_instance).restore()
RestoredPackage(**packaged_instance)()

some.util.package.RedisWhatever(
    db=0,
    channel="example",
    host=some.settings.package.redis.HOST,
    username=some.auth.package.get_redis_username(),
    password=some.auth.package.get_redis_password(),
    handlers={
       "receive": [
          some.processing.package.inform_clients
       ]
    }
```

In the following, let's assume that there are two available subclasses of `some.util.package.RedisWhatever`:
 - `example.implementation.package.extra.words.RedisBasketWeaverWhateverImplementation`
 - `third.party.implementation.FakeWhatever`

## Why use this instead of Pydantic?

`Restorable`s are not meant to replace `Pydantic` and are even intended to work _with_ it. The key features of a 
`Restorable` are that objects can be created via functional values and that instantiation may be done without pure 
understanding of what is to be created on a code level. The focus on `Restorable` is to recreate an _object_, 
whereas `Pydantic` provides tools used to serialize and deserialize complex _data_.

Each concrete implementation of `Restorable` is responsible for communicating what is required to restore it 
within four functions:

```python
    def get_module_name(self) -> str:
        """
        Returns:
            The name of the module that contains the object used to restore this object
        """
        return inspect.getmodule(self.__class__).__name__
    
    def get_restoring_name(self) -> str:
        """
        Returns:
            The name of the function or object used to restore this object
        """
        return self.__class__.__name__

    @abc.abstractmethod
    def get_package_arguments(self) -> typing.List:
        """
        Get positional arguments for the field
        """
        ...

    @abc.abstractmethod
    def get_package_keyword_arguments(self) -> typing.Dict[str, typing.Any]:
        """
        Get keyword arguments for the field
        """
        ...
```

`get_module_name` and `get_restoring_name` are already implemented, but they may be overwritten for different 
functionality, such as leaving room for the creation of environment specific implementations.

Take an object like the following from a package named `example.implementation.package.extra.words`:

```python
class RedisBasketWeaverWhateverImplementation:
    def __init__(self, db, channel, host, username, password, handlers):
        self.db = db
        self.channel = channel
        self.host = host
        self.username = username
        self.password = password
        self.handlers = handlers

redis_weaver = RedisBasketWeaverWhateverImplementation(
    db=0,
    channel="example",
    host=some.settings.package.redis.HOST,
    username=some.auth.package.get_redis_username(),
    password=some.auth.package.get_redis_password(),
    handlers={
       "receive": [
          some.processing.package.inform_clients
       ]
    }
```

The `Pydantic` approach through `RedisBasketWeaverWhateverImplementation` would produce:

```python 
pydantic_version = {
   "db": 0,
   "channel": "example",
   "host": "redis-container",
   "username": "alfred.molina",
   "password": "1'll g3t y0u PiDerM4N!"
}
```

The `handlers` field cannot be included because functions are not `json` serializable.

A `Restorable` version, however, _could_ produce:

```python
restorable_version = {
    "module": "some.util.package",
    "name": "get_redis_whatever",
    "kwargs": {
        "db": 0,
        "channel": "example",
        "host": {
            "module": "some.settings.package",
            "name": "redis.HOST"
        },
        "username": {
            "module": "some.auth.package",
            "name": "get_redis_username"
        },
        "password": {
            "module": "some.auth.package",
            "name": "get_redis_password"
        },
        "handlers": {
            "receive": [
                {
                    "module": "some.processing.package",
                    "name": "inform_clients",
                    "is_function": True
                }
            ]
        }
    }
}
```

if it overwrote `get_module_name` and `get_restoring_name` to look like:

```python
    def get_module_name(self) -> str:
        return "some.util.package"

    def get_restoring_name(self) -> str:
        return "get_redis_whatever"
```

In this hypothetical case, `some.util.package.get_redis_whatever` could return the appropriate class in the 
receiving context. It _could_ create an instance of 
`example.implementation.package.extra.words.RedisBasketWeaverWhateverImplementation` or maybe something like
`third.party.implementation.FakeWhatever` if it were more appropriate in the receiver's environment.

When restoring the `Restorable` version, the same `handlers` will still be available.

## Objects

### `Restorable`

`Restorable` is a base class that provides implementations for 