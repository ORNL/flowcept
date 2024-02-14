
# Branches and Pull Requests

We have two protected branches: `dev` and `main`. This means that these two branches should be as stable as
possible, especially the `main` branch. PRs to them should be peer-reviewed.   

The `main` branch always has the latest working version, with a tagged release published to 
[pypi](https://pypi.org/project/flowcept). 
The `dev` branch may be ahead of `main` while new features are
being implemented. Feature branches should be pull requested to the `dev` branch. Pull requests into the 
`main` branch should always be made from the `dev` branch and be merged when the developers agree it is time
to do so.

# CI/CD Pipeline

## Automated versioning

Flowcept ~~[attempts to]~~ follows semantic versioning.
There is a [GitHub Action](.github/workflows/create-release-n-publish.yml) that automatically bumps the 
patch number of the version at PRs to the main branch and uploads to the package to pypi.

## Automated Tests and Code format check

All human-triggered commits to any branch will launch the [automated tests GitHub Action](.github/workflows/run-unit-tests.yml).
They will also trigger the [code format checks](.github/workflows/code-formatting.yml),
using black and flake8. So, make sure you run the following code before your commits.

```shell
$ black .
$ flake8 .  
```

## Automated Releases

All commits to the `main` branch will launch the [automated publish and release GitHub Action](.github/workflows/create-release-n-publish.yml).
This will create a [tagged release](https://github.com/ORNL/flowcept/releases) and publish the package to [pypi](https://pypi.org/project/flowcept).

# Checklist for Creating a new FlowCept adapter

1. Create a new package directory under `flowcept/flowceptor/plugins`
2. Create a new class that inherits from `BaseInterceptor`, and consider implementing the abstract methods:
    - Observe
    - Intercept
    - Callback
    - Prepare_task_msg
    
See the existing plugins for a reference.

3. [Optional] You may need extra classes, such as 
   local state manager (we provide a generic [`Interceptor State Manager`](flowcept/flowceptor/adapters/interceptor_state_manager.py)),
   `@dataclasses`, Data Access Objects (`DAOs`), and event handlers.

4. Create a new entry in the [settings.yaml](resources/settings.yaml) file and in the [Settings factory](flowcept/commons/settings_factory.py)

5. Create a new `requirements.txt` file under the directory [extra_requirements](extra_requirements) and
adjust the [setup.py](setup.py).

6. [Optional] Add a new constant to [vocabulary.py](flowcept/commons/vocabulary.py).

7. [Optional] Ajust flowcept.__init__.py.


# Issue Labels

When a new issue is created a priority label should be added indicating how important the issue is.

* `priority:low` - syntactic sugar, or addressing small amounts of technical debt or non-essential features
* `priority:medium` - is important to the completion of the milestone but does not require immediate attention
* `priority:high` - is essential to the completion of a milestone

Reference: https://github.com/ORNL/zambeze/blob/main/CONTRIBUTING.md
