#!/usr/bin/python

import random


def hillclimb(init_function, move_operator, objective_function, max_evaluations):
    best = init_function()
    best_score = objective_function(best)

    num_evaluations = 1

    while num_evaluations < max_evaluations:
        # examine moves around our current position
        move_made = False
        for next in move_operator(best):
            if num_evaluations >= max_evaluations:
                break

            # see if this move is better than the current
            next_score = objective_function(next)
            num_evaluations += 1
            if next_score > best_score:
                best = next
                best_score = next_score
                move_made = True
                break  # depth first search

        if not move_made:
            break   # we couldn't find a better move (must be at a local maximum)

    return num_evaluations, best_score, best


def hillclimb_and_restart(init_function, move_operator, objective_function, max_evaluations):
    best = None
    best_score = 0

    num_evaluations = 0
    while num_evaluations < max_evaluations:
        remaining_evaluations = max_evaluations - num_evaluations

        evaluated, score, found = \
            hillclimb(init_function, move_operator, objective_function, remaining_evaluations)

        num_evaluations += evaluated
        if score > best_score or best is None:
            best_score = score
            best = found

    return num_evaluations, best_score, best


def rand_seq(size):
    '''generates values in random order
    equivalent to using shuffle in random,
    without generating all values at once'''
    values = range(size)
    for i in xrange(size):
        # pick a random index into remaining values
        j = i + int(random.random() * (size - i))
        # swap the values
        values[j], values[i] = values[i], values[j]
        # return the swapped value
        yield values[i]


def all_pairs(size):
    '''generates all i,j pairs for i,j from 0-size'''
    for i in rand_seq(size):
        for j in rand_seq(size):
            yield (i, j)


def reversed_sections(tour):
    '''generator to return all possible variations where the section between two cities are swapped'''
    for i, j in all_pairs(len(tour)):
        if i != j:
            copy = tour[:]
            if i < j:
                copy[i:j + 1] = reversed(tour[i:j + 1])
            else:
                copy[i + 1:] = reversed(tour[:j])
                copy[:j] = reversed(tour[i + 1:])
            if copy != tour:  # no point returning the same tour
                yield copy


def swapped_cities(tour):
    '''generator to create all possible variations where two cities have been swapped'''
    for i, j in all_pairs(len(tour)):
        if i < j:
            copy = tour[:]
            copy[i], copy[j] = tour[j], tour[i]
            yield copy


#   TODO: Replace this with one that uses specific weight functions
def cartesian_matrix(tracks, dist):
    '''create a distance matrix for the city coords that uses straight line distance'''
    matrix = {}
    for i, t1 in enumerate(tracks):
        for j, t2 in enumerate(tracks):
            matrix[i, j] = dist(t1, t2)
    return matrix


def tour_length(matrix, tour):
    '''total up the total length of the tour based on the distance matrix'''
    total = 0
    num_cities = len(tour)
    for i in range(num_cities):
        j = (i + 1) % num_cities
        city_i = tour[i]
        city_j = tour[j]
        total += matrix[city_i, city_j]
    return total


def init_random_tour(tour_length):
    tour = range(tour_length)
    random.shuffle(tour)
    return tour


def solve(tracks, dist, max_iterations=10000):
    move_operator = reversed_sections

    init_function = lambda: init_random_tour(len(tracks))
    matrix = cartesian_matrix(tracks, dist)
    objective_function = lambda tour: -tour_length(matrix, tour)

    iterations, score, best = \
        hillclimb_and_restart(init_function, move_operator, objective_function, max_iterations)
    return best
