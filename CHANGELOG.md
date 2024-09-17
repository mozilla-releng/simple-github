## 2.1.0 (2024-09-17)

### Feat

- support unauthenticated access to the Github API

## 2.0.0 (2024-09-13)

### Feat

- make `client.request` return response object rather than content

## 1.0.0 (2023-12-13)

### Feat

- add support for synchronous environments

## 0.2.0 (2023-11-02)

### Feat

- add methods for 'PUT', 'PATCH' and 'DELETE' requests

## 0.1.3 (2023-10-27)

### Fix

- ensure 'AppInstallationAuth' closes its internal client

## 0.1.2 (2023-10-23)

### Feat

- rename 'client._make_request' to 'client.request'

### Fix

- stop using 'TypeAlias' to support older Pythons

## 0.1.1 (2023-10-22)

### Feat

- implement Github client with authentication

### Fix

- use 'TypeAlias' for compatibility with older Pythons
- don't assume responses are json

### Refactor

- use custom type for REST api responses
