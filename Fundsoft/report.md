# Report for assignment 3

This is a template for your report. You are free to modify it as needed.
It is not required to use markdown for your report either, but the report
has to be delivered in a standard, cross-platform format.

## Project

Name: PDM

URL: https://github.com/pdm-project/pdm

A package manager for python projects.

## Onboarding experience

Did it build and run as documented?
    
See the assignment for details; if everything works out of the box,
there is no need to write much here. If the first project(s) you picked
ended up being unsuitable, you can describe the "onboarding experience"
for each project, along with reason(s) why you changed to a different one.

PDM was the first project we picked.

The project has a good CONTRIBUTING.md, where clear instructions are given
on how to organize ones contribution. The project recomends using it's own 
product (PDM) to ensure formatting and linting. Changes are documented using 
`news` fragments. 


## Complexity

1. What are your results for ten complex functions?
   * Did all methods (tools vs. manual count) get the same result?
   * Are the results clear?
2. Are the functions just complex, or also long?
3. What is the purpose of the functions?
4. Are exceptions taken into account in the given measurements?
5. Is the documentation clear w.r.t. all the possible outcomes?

## Refactoring

Plan for refactoring complex code:

Every group member has written their refactoring plan in a markdown file located in the Fundsoft/Refactoring-plans folder. 
[Refactoring-plans](https://github.com/KTH-DD2480-Fundsoft/pdm-assignment-3/tree/report/Fundsoft/Refactoring-plans)

Estimated impact of refactoring (lower CC, but other drawbacks?).

When it comes to refactoring we found that many of the functions could be re-written. Not necessarily shortened where we get rid of unnecessary conditional statements but more that independent blocks of code could be moved outside of the function so that they formed separate functions. Since we didn't want to damage the logic of the functions by trying to optimize the logic of the code we focused on splitting complex functions into several smaller and less complex functions that could be called on by each other. Some positive benefits of this entail shorter functions making them easier to read and understand. Another benefit could be that independent functions can be isolated into their own function and thus be able to be called upon by other functions. Some negative drawbacks of this would be that splitting up a function makes it necessary to read several other functions instead of just one function. If one splits up the function too much this could become overwhelming. 


Carried out refactoring (optional, P+):

The implemented versions of the refactoring can be see on the branch feature/65/refactor. Url shortcuts are given below:

[Victor - Refactoring P+](https://github.com/pdm-project/pdm/commit/16b835b7d853d707b6126a9d4641e7470aae0334)

[Ludvig - Refactoring P+](https://github.com/pdm-project/pdm/commit/1a60ede32dd73e84ed31e6c7f991106b723f797b)

[Rasmus - Refactoring P+](https://github.com/pdm-project/pdm/commit/f2e3836356304d89f490a3ca2f4f87d488bb29fe)

[Sebastian - Refactoring P+]()

[Dante - Refactoring P+]()


## Coverage

### Tools

Document your experience in using a "new"/different coverage tool.

How well was the tool documented? Was it possible/easy/difficult to
integrate it with your build environment?

### Your own coverage tool

Show a patch (or link to a branch) that shows the instrumented code to
gather coverage measurements.

The patch is probably too long to be copied here, so please add
the git command that is used to obtain the patch instead:

git diff ...

What kinds of constructs does your tool support, and how accurate is
its output?

### Evaluation

1. How detailed is your coverage measurement?

2. What are the limitations of your own tool?

3. Are the results of your tool consistent with existing coverage tools?

## Coverage improvement

Show the comments that describe the requirements for the coverage.

Report of old coverage: [link]

Report of new coverage: [link]

Test cases added:

git diff ...

Number of test cases added: two per team member (P) or at least four (P+).

## Self-assessment: Way of working

Current state according to the Essence standard: ...

Was the self-assessment unanimous? Any doubts about certain items?

How have you improved so far?

Where is potential for improvement?

## Overall experience

What are your main take-aways from this project? What did you learn?

Is there something special you want to mention here?
