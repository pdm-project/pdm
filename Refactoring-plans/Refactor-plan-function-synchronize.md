# Refactoring the function `synchronize` from synchronize@385-467@./src/pdm/installers/synchronizers.py

## Idea 
This markdown file is dedicated to refactoring the `syncronize` function into smaller units so as to lower the Cyclomatic Complexity (CCN) of the function. The aim being to improve readability and simplify unittesting. Below you will find a detailed description of the function, identification of its different components, what the function does along with a concrete example of how to split up the code

### The `synchronize` function
The `synchronize`function belongs to the class `Synchronizer` and can be found in `./src/pdm/installers/synchronizers.py` of the pdm repository. The function is 82 lines long and looks like this:

```python
def synchronize(self) -> None:
        to_add, to_update, to_remove = self.compare_with_working_set()
        to_do = {"remove": to_remove, "update": to_update, "add": to_add}

        if self.dry_run: 
            self._show_summary(to_do)
            return

        self._show_headline(to_do)
        handlers = {
            "add": self.install_candidate,
            "update": self.update_candidate,
            "remove": self.remove_distribution,
        }
        sequential_jobs = []
        parallel_jobs = []

        for kind in to_do: 
            for key in to_do[kind]: 
                if key in self.SEQUENTIAL_PACKAGES: 
                    sequential_jobs.append((kind, key)) 
                elif key in self.candidates and self.candidates[key].req.editable: 
                    # Editable packages are installed sequentially.
                    sequential_jobs.append((kind, key))
                else:
                    parallel_jobs.append((kind, key))

        state = SimpleNamespace(errors=[], failed_jobs=[], jobs=[], mark_failed=False)

        def update_progress(future: Future | DummyFuture, kind: str, key: str) -> None:
            error = future.exception()
            if error: 
                exc_info = (type(error), error, error.__traceback__)
                termui.logger.exception("Error occurs: ", exc_info=exc_info)
                state.failed_jobs.append((kind, key))
                state.errors.extend([f"{kind} [success]{key}[/] failed:\n", *traceback.format_exception(*exc_info)])
                if self.fail_fast: 
                    for future in state.jobs: 
                        future.cancel()
                    state.mark_failed = True

        # get rich progress and live handler to deal with multiple spinners
        with self.ui.make_progress( 
            " ",
            SpinnerColumn(termui.SPINNER, speed=1, style="primary"),
            "{task.description}",
            "[info]{task.fields[text]}",
            TaskProgressColumn("[info]{task.percentage:>3.0f}%[/]"),
        ) as progress:
            live = progress.live
            for kind, key in sequential_jobs: 
                handlers[kind](key, progress)
            for i in range(self.retry_times + 1): 
                state.jobs.clear()
                with self.create_executor() as executor:
                    for kind, key in parallel_jobs: 
                        future = executor.submit(handlers[kind], key, progress)
                        future.add_done_callback(functools.partial(update_progress, kind=kind, key=key))
                        state.jobs.append(future)
                if state.mark_failed or not state.failed_jobs or i == self.retry_times: 
                    break
                parallel_jobs, state.failed_jobs = state.failed_jobs, []
                state.errors.clear()
                live.console.print("Retry failed jobs")

            if state.errors: 
                if self.ui.verbosity < termui.Verbosity.DETAIL: 
                    live.console.print("\n[error]ERRORS[/]:")
                    live.console.print("".join(state.errors), end="")
                raise InstallationError("Some package operations are not complete yet")

            if self.install_self:
                self_key = self.self_key
                assert self_key 
                self.candidates[self_key] = self.self_candidate
                word = "a" if self.no_editable else "an editable" 
                live.console.print(f"Installing the project as {word} package...")
                if self_key in self.working_set: 
                    self.update_candidate(self_key, progress)
                else:
                    self.install_candidate(self_key, progress)

            live.console.print(f"\n{termui.Emoji.POPPER} All complete!")

```

### Identifying submodules

We begin by looking at the code block by block in the hope of identifying independent blocks that coulde be transferred to an external function as well as understanding how the function operates. The line references below refer to the lines in the function itself where line 1 is the function definition itself (```def synchronize(self) -> None:```)

#### Lines 1-14
``` python
def synchronize(self) -> None:
        to_add, to_update, to_remove = self.compare_with_working_set()
        to_do = {"remove": to_remove, "update": to_update, "add": to_add}

        if self.dry_run: 
            self._show_summary(to_do)
            return

        self._show_headline(to_do)
        handlers = {
            "add": self.install_candidate,
            "update": self.update_candidate,
            "remove": self.remove_distribution,
        }
```
In the beginning of the function we see how the function recieves multiple inputs from another function. These inputs refer to which packages pdm should "add", "update" or "remove" from the local environment. The function then creates a "to-do" dictionary where each package is mapped to its respective key "remove", "update" or "add". On line 5 we see our first branch in the function where if self.dry_run is true we return. The function then creates another dict which matches each respective "install", "update" or "remove" function to the same keys as before. Not much CCN or complexity can be optimized here.

#### Lines 15-27
```python
        sequential_jobs = []
        parallel_jobs = []

        for kind in to_do: 
            for key in to_do[kind]: 
                if key in self.SEQUENTIAL_PACKAGES: 
                    sequential_jobs.append((kind, key)) 
                elif key in self.candidates and self.candidates[key].req.editable: 
                    # Editable packages are installed sequentially.
                    sequential_jobs.append((kind, key))
                else:
                    parallel_jobs.append((kind, key))
```
The next part of our function includes the following code. We see that we create two lists and later append different packages to "sequential_jobs" or "parallel_jobs" depending on if the packages fulfill certain requirements. All that this block of code does is that it appends different packages to one of two lists. This block adds a CCN complexity of 4 the to `synchronize` function. This independent block of code can be moved to an external function as it only requires the dict "to_do" along with a `self` access to the object. We can lower the CCN by 4 and remove 12 LOC this way. 

#### Lines 28-41

``` python
        state = SimpleNamespace(errors=[], failed_jobs=[], jobs=[], mark_failed=False)

        def update_progress(future: Future | DummyFuture, kind: str, key: str) -> None:
            error = future.exception()
            if error: 
                exc_info = (type(error), error, error.__traceback__)
                termui.logger.exception("Error occurs: ", exc_info=exc_info)
                state.failed_jobs.append((kind, key))
                state.errors.extend([f"{kind} [success]{key}[/] failed:\n", *traceback.format_exception(*exc_info)])
                if self.fail_fast: 
                    for future in state.jobs: 
                        future.cancel()
                    state.mark_failed = True
```
In this block of code we create a `SimpleNameSpace` object which is later used to store errors, failed downloads, a list of remaining jobs as well as a bool which is used to quickly check if a download failed. We then find a nested function inside of our function. Now nested functions can be a nice way of accessing internal variables in an easy way. This function could however be useful for other functions. If we move this function out we can further reduce the CCN complexity of `synchronize` by 3 along with providing other functions access to the `update_progress` function. We will however keep the object state in `synchronize`.

#### Lines 42-82

``` python

        # get rich progress and live handler to deal with multiple spinners
        with self.ui.make_progress( 
            " ",
            SpinnerColumn(termui.SPINNER, speed=1, style="primary"),
            "{task.description}",
            "[info]{task.fields[text]}",
            TaskProgressColumn("[info]{task.percentage:>3.0f}%[/]"),
        ) as progress:
            live = progress.live
            for kind, key in sequential_jobs: 
                handlers[kind](key, progress)
            for i in range(self.retry_times + 1): 
                state.jobs.clear()
                with self.create_executor() as executor:
                    for kind, key in parallel_jobs: 
                        future = executor.submit(handlers[kind], key, progress)
                        future.add_done_callback(functools.partial(update_progress, kind=kind, key=key))
                        state.jobs.append(future)
                if state.mark_failed or not state.failed_jobs or i == self.retry_times: 
                    break
                parallel_jobs, state.failed_jobs = state.failed_jobs, []
                state.errors.clear()
                live.console.print("Retry failed jobs")

            if state.errors: 
                if self.ui.verbosity < termui.Verbosity.DETAIL: 
                    live.console.print("\n[error]ERRORS[/]:")
                    live.console.print("".join(state.errors), end="")
                raise InstallationError("Some package operations are not complete yet")

            if self.install_self:
                self_key = self.self_key
                assert self_key 
                self.candidates[self_key] = self.self_candidate
                word = "a" if self.no_editable else "an editable" 
                live.console.print(f"Installing the project as {word} package...")
                if self_key in self.working_set: 
                    self.update_candidate(self_key, progress)
                else:
                    self.install_candidate(self_key, progress)

            live.console.print(f"\n{termui.Emoji.POPPER} All complete!")

```
The last code block contains the main functionality of the function with all the actual installations and error handling. Even if this block is somewhat complex with a CCN complexity of 10 it is reasonalbe to leave it as is since this contains all the actaully necessay features corresponding to the purpose of the function `synchronize` which is to actaully "install", "remove" and "update" different packages.

## Refactor
Thus one way to refactor this code is to split it up into the following 3 functions:
* `syncronize()`: CCN complexity of 11, LOC = 62
* `catalogue_packages()`: CCN complexity of 5, LOC = 13
* `update_progress()`: CCN complexity of 4, LOC = 13


``` diff
# CCN complexity of 11, LOC = 62
def synchronize(self) -> None:
    to_add, to_update, to_remove = self.compare_with_working_set()
    to_do = {"remove": to_remove, "update": to_update, "add": to_add}

    if self.dry_run: 
        self._show_summary(to_do)
        return

    self._show_headline(to_do)
    handlers = {
        "add": self.install_candidate,
        "update": self.update_candidate,
        "remove": self.remove_distribution,
    }

-    sequential_jobs = []
-    parallel_jobs = []

-    for kind in to_do: #2
-        for key in to_do[kind]: #3
-            if key in self.SEQUENTIAL_PACKAGES: #4
-                sequential_jobs.append((kind, key)) 
-            elif key in self.candidates and self.candidates[key].req.editable: #5
-                # Editable packages are installed sequentially.
-                sequential_jobs.append((kind, key))
-            else:
-                parallel_jobs.append((kind, key))

+    sequential_jobs, parallel_jobs = catalogque_packages(to_do)
    state = SimpleNamespace(errors=[], failed_jobs=[], jobs=[], mark_failed=False)

-    def update_progress(future: Future | DummyFuture, kind: str, key: str) -> None:
-        error = future.exception()
-        if error: #6
-            exc_info = (type(error), error, error.__traceback__)
-            termui.logger.exception("Error occurs: ", exc_info=exc_info)
-            state.failed_jobs.append((kind, key))
-            state.errors.extend([f"{kind} [success]{key}[/] failed:\n", *traceback.format_exception(*exc_info)])
-            if self.fail_fast: #7
-                for future in state.jobs: #8
-                    future.cancel()
-                state.mark_failed = True


    # get rich progress and live handler to deal with multiple spinners
    with self.ui.make_progress( 
        " ",
        SpinnerColumn(termui.SPINNER, speed=1, style="primary"),
        "{task.description}",
        "[info]{task.fields[text]}",
        TaskProgressColumn("[info]{task.percentage:>3.0f}%[/]"),
    ) as progress:
        live = progress.live
        for kind, key in sequential_jobs: 
            handlers[kind](key, progress)
        for i in range(self.retry_times + 1): 
            state.jobs.clear()
            with self.create_executor() as executor:
                for kind, key in parallel_jobs: 
                    future = executor.submit(handlers[kind], key, progress)
-                    future.add_done_callback(functools.partial(update_progress, kind=kind, key=key))
+                    future.add_done_callback(functools.partial(self.update_progress, kind=kind, key=key))
                    state.jobs.append(future)
            if state.mark_failed or not state.failed_jobs or i == self.retry_times: 
                break
            parallel_jobs, state.failed_jobs = state.failed_jobs, []
            state.errors.clear()
            live.console.print("Retry failed jobs")

        if state.errors: 
            if self.ui.verbosity < termui.Verbosity.DETAIL: 
                live.console.print("\n[error]ERRORS[/]:")
                live.console.print("".join(state.errors), end="")
            raise InstallationError("Some package operations are not complete yet")

        if self.install_self:
            self_key = self.self_key
            assert self_key 
            self.candidates[self_key] = self.self_candidate
            word = "a" if self.no_editable else "an editable" 
            live.console.print(f"Installing the project as {word} package...")
            if self_key in self.working_set: 
                self.update_candidate(self_key, progress)
            else:
                self.install_candidate(self_key, progress)

        live.console.print(f"\n{termui.Emoji.POPPER} All complete!")

```


```diff
# CCN complexity of 5, LOC = 13
+ def catalogue_packages(self, to_do: Dict): 
+    sequential_jobs = []
+    parallel_jobs = []

+    for kind in to_do: 
+        for key in to_do[kind]: 
+            if key in self.SEQUENTIAL_PACKAGES: 
+                sequential_jobs.append((kind, key)) 
+            elif key in self.candidates and self.candidates[key].req.editable: 
+                # Editable packages are installed sequentially.
+                sequential_jobs.append((kind, key))
+            else:
+                parallel_jobs.append((kind, key))
+    return sequential_jobs, parallel_jobs
```

```diff
# CCN complexity of 4, LOC = 13
+ def update_progress(self, future: Future | DummyFuture, kind: str, key: str) -> None: 
+    error = future.exception()
+    if error: 
+        exc_info = (type(error), error, error.__traceback__)
+        termui.logger.exception("Error occurs: ", exc_info=exc_info)
+        state.failed_jobs.append((kind, key))
+        state.errors.extend([f"{kind} [success]{key}[/] failed:\n", *traceback.format_exception(*exc_info)])
+        if self.fail_fast: 
+            for future in state.jobs: 
+                future.cancel()
+            state.mark_failed = True
+    return state
```

## Results
If we were to refactor the `syncronize` function in this way then we would reduce its Cyclomatic Complexity from 18 to 11 which is a decrease of 7/18 = 0.39 = 39%. The functions LOC would also decrease from 82 to 52. We would recieve 3 functions with a CCN of 11, 5, 4 respectively instead of 1 function with a CCN = 18. The 3 functions would have an LOC of 62, 13, 13 respectively which is 88 and only 6 lines of code more than the original function. 